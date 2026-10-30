"""Verify tokens with Supabase Auth, then read the caller's current database role.

No JWT is trusted by decoding it locally. No service-role credential is needed.
Every request validates identity remotely; role revocation takes effect on the
next request because the role comes from SQL, not mutable or stale JWT metadata.
"""

from typing import Annotated, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ValidationError

bearer = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/api/v1", tags=["Identity"])


class Identity(BaseModel):
    id: UUID
    email: str
    role: Literal["member", "admin"]


def get_auth_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.supabase


def unauthorized() -> HTTPException:
    return HTTPException(401, "Sign in again to continue.", headers={"WWW-Authenticate": "Bearer"})


async def require_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    client: Annotated[httpx.AsyncClient, Depends(get_auth_client)],
) -> Identity:
    if credentials is None:
        raise unauthorized()
    config = request.app.state.settings
    if not config.auth_configured:
        raise HTTPException(503, "Supabase authentication is not configured.")
    token = credentials.credentials
    if len(token) > 16384:
        raise unauthorized()
    headers = {
        "apikey": config.supabase_publishable_key.get_secret_value(),
        "Authorization": f"Bearer {token}",
    }
    try:
        # This trusted, fixed-project endpoint verifies the token on the Auth server.
        user_response = await client.get(f"{config.supabase_url}/auth/v1/user", headers=headers)
        if user_response.status_code in {401, 403}:
            raise unauthorized()
        user_response.raise_for_status()
        user = user_response.json()
        if not isinstance(user, dict) or user.get("is_anonymous", False):
            raise unauthorized()
        user_id = UUID(user["id"])
        email = user["email"]
        if not isinstance(email, str) or not email or not user.get("email_confirmed_at"):
            raise unauthorized()
        # The RPC has no user-id argument: SQL scopes it to auth.uid() from this token.
        role_response = await client.post(
            f"{config.supabase_url}/rest/v1/rpc/current_user_role", headers=headers, json={}
        )
        if role_response.status_code in {401, 403}:
            raise unauthorized()
        role_response.raise_for_status()
        return Identity(id=user_id, email=email, role=role_response.json())
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError) as error:
        # Never expose the upstream body, tokens, API keys, or connection details.
        raise HTTPException(
            503, "Identity verification is unavailable. Try again shortly."
        ) from error


async def require_admin(identity: Annotated[Identity, Depends(require_identity)]) -> Identity:
    if identity.role != "admin":
        raise HTTPException(403, "Administrator access is required.")
    return identity


@router.get("/me", response_model=Identity)
async def me(identity: Annotated[Identity, Depends(require_identity)]) -> Identity:
    return identity


@router.get("/admin/status")
async def admin_status(identity: Annotated[Identity, Depends(require_admin)]) -> dict[str, str]:
    return {"status": "authorized", "scope": "administrator", "user_id": str(identity.id)}
