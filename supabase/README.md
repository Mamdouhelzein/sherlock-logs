# Supabase setup — identity and access

The integration is implemented; a hosted project is **not provisioned by this repository**. Public pages work without configuration. Sign-in forms stay disabled until a project is configured. No service-role or secret API key is needed for this milestone.

## 1. Create a development project

1. Sign in at [Supabase](https://supabase.com/dashboard) using your own account.
2. Choose your organization and create a project named `sherlock-logs-dev`. Choose your region and an appropriate available plan. Set and store the database password privately; the application does not need it.
3. Wait for the project to finish provisioning.
4. Copy the **Project URL** and **publishable API key** from the project's connection/API settings. The key should start with `sb_publishable_`. This integration intentionally rejects secret keys and legacy JWT keys.

## 2. Apply the identity migration

Open the project's SQL Editor, paste [migrations/202610300001_identity.sql](migrations/202610300001_identity.sql), and run it once. Alternatively apply it using your normal Supabase CLI migration workflow. Do not paste the test bootstrap into a hosted project.

The migration creates:

- `public.profiles`: private profile per user, with a bounded display name. Users can select their own row and update only its display name.
- `private.user_roles`: trusted administrator assignments, inaccessible to browser roles. Keep `private` out of the project's exposed Data API schemas.
- `public.current_user_role()`: an authenticated-only RPC returning **the caller's** current role. It has no user-id parameter. Missing assignments mean `member`.
- A trigger creating profiles for new users, plus a backfill for existing users.

Role helpers use fixed schema-qualified SQL and an empty search path. User metadata never controls privileges. RLS and column grants apply even when clients call Supabase directly.

## 3. Configure email authentication

In Authentication settings:

1. Enable email/password sign-in and keep **email confirmation enabled**. The API requires a confirmed email and rejects anonymous accounts.
2. Set the development **Site URL** to `http://127.0.0.1:5173`.
3. Add these exact allowed redirect URLs:
   - `http://127.0.0.1:5173/auth/callback`
   - `http://127.0.0.1:5173/reset-password`
4. Set minimum password length to at least 12, matching the account creation form. Review the project's authentication rate limits and email delivery restrictions. For sending beyond provider development restrictions, configure your own SMTP provider.

Use one hostname consistently. If using `localhost`, add its corresponding Site URL/redirects and start requests there. Production requires your actual HTTPS origin and exact callback URLs.

The client uses PKCE and Supabase's automatic code exchange. Open confirmation and recovery links in the same browser and origin where you requested them, so the stored verifier is available. Expired or invalid links produce recovery guidance. Custom email templates must preserve the provider's confirmation flow and redirect destination.

## 4. Set local configuration

Copy the root `.env.example` to `.env`, then uncomment and replace all four values:

```dotenv
VITE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_KEY
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_KEY
```

Use the same project and key in both services. Keep `.env` untracked. All `VITE_` values are public browser configuration. Never put a secret or service-role key in them. Restart both services after changes; rebuild the frontend if using Compose.

The API validates bearer tokens by calling the fixed project's `/auth/v1/user` endpoint, then calls the role RPC using **that same user token**. Upstream failures deny access. No browser identity object or locally decoded JWT grants access. The API needs outbound HTTPS access to your project.

## 5. Verify real sign-in

1. Open `/register`, create a development account, and open the email confirmation link in the same browser.
2. Verify `/account` loads a server-verified identity and your private profile. Edit the display name, reload, and check that it persisted.
3. Open `/admin` as a member: access must be denied. Calling `GET /api/v1/admin/status` directly with a member token must also return 403.
4. Sign out, then open `/account` directly: it must return to sign-in.
5. Request recovery at `/forgot-password`, follow its email link, and update the password.
6. Try a second development account and confirm it cannot read or update the first account's profile. Apply the administrator steps below and verify revocation.
7. Exercise invalid passwords and confirm the project's configured rate limits. Browser mock tests do not establish hosted rate-limit or email-delivery behavior.

The public status endpoint only reports whether backend project settings are present. **“Settings present” is not a live authentication or migration readiness probe.** Login events and ML scores are not collected yet.

## Administrator assignment

Register and confirm the intended account first. In your trusted SQL Editor, replace the email below with the exact account email:

```sql
insert into private.user_roles (user_id, role)
select id, 'admin' from auth.users where email = 'YOUR-ACCOUNT-EMAIL'
on conflict (user_id) do update set role = excluded.role, updated_at = now();
```

Confirm the query affected the intended row. Reload `/admin` to check access. Never expose a public promotion endpoint or put an admin selector in registration.

To revoke administrator access:

```sql
delete from private.user_roles
where user_id in (select id from auth.users where email = 'YOUR-ACCOUNT-EMAIL');
```

The API reads the current role on every protected request, so revocation does not wait for a JWT metadata refresh. The browser display may need a refresh; backend authorization is authoritative.

## Tests and limits

CI runs the migration and [identity authorization checks](tests/identity.sql) on disposable PostgreSQL 17 with a minimal Auth fixture. It checks profile isolation, denied client inserts/deletes, self-promotion rejection, metadata forgery, trusted promotion, and revocation. [tests/bootstrap.sql](tests/bootstrap.sql) is **CI-only**, not a Supabase migration. A clean hosted-project verification is still required for actual Supabase Auth, redirect configuration, emails, and project-specific grants.

Backend tests mock Auth/Data API responses to check invalid tokens, outages, unconfirmed accounts, role checks, and revocation. Browser tests use the real Supabase JS client against mocked provider responses for sign-in, PKCE, recovery, persistence, and sign-out. No test credentials grant access in a running deployment.

Sessions persist in browser storage for this SPA. Avoid untrusted scripts and clear sessions on shared computers. This is single-project access control; organization tenancy, mandatory MFA, event retention, and investigation tables are later work. Authentication stays independent of ML.

References: [Supabase user verification](https://supabase.com/docs/reference/javascript/auth-getuser), [PKCE](https://supabase.com/docs/guides/auth/sessions/pkce-flow), [Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security), [database functions](https://supabase.com/docs/guides/database/functions).
