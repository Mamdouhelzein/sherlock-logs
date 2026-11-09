# Public beta deployment

Status, 2026-11-10: **not publicly deployed**. The two-container package is
implemented and the original synthetic v1 model is published as a pinned
prerelease. Hosting signup, actual free resource availability, production email,
public flow verification and restoration testing remain pending. A successful
image build or GitHub release is not a working public service.

## Target and cost boundary

The target is **Northflank Sandbox**. Its [current pricing page](https://northflank.com/pricing)
advertises no card, no sleeping, two services, two jobs, one database and up to
$20/month in included resources. Confirm account eligibility, memory, storage
and traffic in the dashboard before provisioning. Older provider billing docs
still mention card verification; the actual resource-creation flow must settle
that discrepancy. Do not upgrade, add a card, depend on trial credits, select
BYOC or accept billable overages. Sandbox has no uptime SLA.

Northflank supplies a `code.run` HTTPS hostname; buying a domain is unnecessary.
A separate transactional email account and verified sender are still required.
[Brevo Free](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan)
is a candidate with 300 emails/day, subject to account and sender approval; it
is not connected. Free-email senders may be
[rewritten by the provider](https://help.brevo.com/hc/en-us/articles/16045394674066-Troubleshooting-Domain-authentication).
Verify actual confirmation and recovery delivery before opening registration.

## Layout and security boundaries

| Resource | Contents | Exposure |
| --- | --- | --- |
| Portal | Existing React build, Nginx, GoTrue and PostgREST | Only port 8080 through Northflank public HTTPS ingress |
| Runtime | FastAPI, 30-second collector, continuous pinned v1 worker | Port 8000 private to the project; portal proxies `/api/v1/` |
| PostgreSQL 17 | New isolated accounts and event database with TLS | Private project network only |
| Cleanup job | Existing bounded 30-day retention function | No listener; every minute, with hourly/backlog timing enforced by SQL |

Choose only Sandbox sizes that pass measured memory and latency checks. No
Northflank resource size is verified yet. Scientific-library threads are limited
to one. The API login is read-only; ingestion, audit reading, scoring and cleanup
have separate roles and child environments. No running service receives a
database owner credential. Sibling processes share a container and Unix user;
filtering environments is not isolation from a compromised sibling. This is a
constrained experimental beta, not an independently assessed security service.

Auth and REST bind to loopback inside the portal. Browser requests still use
user JWTs and RLS; the public configuration key grants no admin rights. Auth
management/metrics have no public route. Exact HTTPS callbacks, confirmation,
refresh-token rotation and the existing five-failure/15-minute account cooldown
remain enabled. Registration starts **disabled** until setup is verified.

The gateway trusts only Northflank's overwritten `X-Envoy-External-Address`,
replaces forwarded headers and rejects Auth requests if the header is absent.
See the [provider's header contract](https://northflank.com/docs/v1/application/network/networking-on-northflank).
Port 8080 must receive traffic only through public HTTP ingress. Do not add raw
TCP exposure or an untrusted internal proxy that can forge this header.

## Operator sequence

This is a runbook, not a record of completed cloud deployment. Existing local
and hosted accounts, role choices and histories are not migrated. Never copy
either existing environment file into the new deployment.

1. Complete the user's Northflank signup, select Sandbox and verify the entire
   layout is available at zero cost without a card. Create a new project and an
   **empty PostgreSQL 17 addon**, with TLS on and public database exposure off.
2. Generate fresh private configuration from repository root:

   ```sh
   PYTHONPATH=backend/src backend/.venv/bin/python tools/cloud_beta.py init
   ```

   This exclusively creates ignored `.env.public-beta.local`, mode 0600, with
   fresh signing/public keys and role passwords. It refuses an existing file.
   Fill `ADMIN_DATABASE_URL` using the provider's supported private connection
   or forwarding flow, with `sslmode=verify-full` and a CA path valid on the
   operator's computer. Setup rejects local/hosted Supabase endpoints, existing
   application tables and conflicting realm IDs. Keep this connection local.
   Set `DATABASE_HOST` and `DATABASE_PORT` to the addon's actual private runtime
   endpoint, independently of the operator's forwarding address and port.
3. Prepare Auth/REST roles before GoTrue's first start:

   ```sh
   PYTHONPATH=backend/src backend/.venv/bin/python tools/cloud_beta.py roles
   ```

   Reserve the portal's HTTPS hostname and create the private runtime service.
   Set `PUBLIC_ORIGIN` to that exact origin and `API_UPSTREAM` to the private
   runtime hostname on port 8000. Build the portal with that same origin/public
   key; runtime rejects a mismatched frontend build.
4. Configure an approved SMTP account/sender and start the portal with
   `REGISTRATION_ENABLED=false`. GoTrue initializes its provider schema.
   Sign-in fails closed while the password hook is not yet installed.
5. Apply application migrations and restricted service roles:

   ```sh
   PYTHONPATH=backend/src backend/.venv/bin/python tools/cloud_beta.py schema
   ```

   Migration digests are recorded atomically. Replay preserves accounts,
   profiles and cooldowns; changed applied migrations are rejected. Runtime
   connections use the images' Linux system CA bundle. Verify actual TLS
   hostname matching. Accounts default to Member; setup does not grant admins.
6. Start/restart the runtime and verify collection/scoring using a separately
   authorized test administrator. The original
   [synthetic shadow model v1](https://github.com/Mamdouhelzein/sherlock-logs/releases/tag/shadow-model-v1)
   is downloaded at build time and hash checked before loading. Bundle pin:
   `deafc493f2d8f5507885534f2bfc3ddb09f3ccd171104c0968deec7519f0ea7c`.
   The rejected v2 stays inactive. ML does not block logins or send alerts.
7. With disposable accounts, verify actual confirmation/recovery delivery,
   PKCE, sign-in/session restoration/logout, two-account profile isolation,
   Member denial at investigator APIs, role revocation, provider-enforced
   cooldown, rejection collection/scoring and forged-header rejection.
   Temporarily enabling signup for controlled tests is not a public launch.
8. Configure private backups, rehearse restoration in another disposable DB,
   verify restart persistence and measured free-tier resource use. Review edge
   logging: application settings cannot control a provider's callback URL logs.
9. Obtain approval for the cloud 30-day policy before activating cleanup;
   installation leaves deletion disabled. After approval:

   ```sh
   PYTHONPATH=backend/src backend/.venv/bin/python tools/cloud_beta.py enable-cleanup
   ```

   Schedule `python /app/tools/beta_cleanup.py` using the runtime image and only
   `CLEANUP_DATABASE_URL`. SQL controls hourly/backlog timing and bounded work.
10. After required checks pass, set `REGISTRATION_ENABLED=true`, verify the
    public pages from an independent browser and share the actual verified URL
    as an experimental beta. Keep signup closed if a required flow fails.

## Builds and secrets

Build from repository root; only public settings enter the browser build:

```sh
docker build -f deploy/northflank/Portal.Dockerfile \
  --build-arg PUBLIC_ORIGIN=https://YOUR-PORTAL.code.run \
  --build-arg PUBLIC_KEY=YOUR_PUBLIC_CONFIGURATION_KEY -t sherlock-beta-portal .
docker build -f deploy/northflank/Runtime.Dockerfile -t sherlock-beta-runtime .
```

| Destination | Settings |
| --- | --- |
| Portal runtime only | `PUBLIC_ORIGIN`, `PUBLIC_KEY`, `API_UPSTREAM`, `JWT_SECRET`, `AUTH_DATABASE_URL`, `REST_DATABASE_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `REGISTRATION_ENABLED` |
| Runtime service only | `PUBLIC_ORIGIN`, `PUBLIC_KEY`, `API_DATABASE_URL`, `INGEST_DATABASE_URL`, `AUDIT_DATABASE_URL`, `SCORING_DATABASE_URL` |
| Cleanup job only | `CLEANUP_DATABASE_URL` |
| Private local operator only | `ADMIN_DATABASE_URL`, `REALM_ID`, generated role passwords |

Never link the entire local configuration as a cloud secret group. Inject only
the destination's listed runtime values. The launcher rejects an injected owner
URL. Private environments and operational state are excluded from Git/builds.
Request logs/provider output are suppressed because callbacks carry credentials.
Supervisor, collector, worker and cleanup output contains status/aggregate
counts only. Provider edge logging requires separate review.

## Verification limits

Local checks cover configuration failure, credential/source separation,
bootstrap replay and role restrictions, Linux v1 model compatibility and the
rendered non-root gateway with fictional upstreams. The new `cloud-packaging`
CI job complements the existing real-Auth integration suite. These checks do
not establish real SMTP delivery, host quotas, cloud TLS, backup restoration,
public uptime, tenant isolation or real-world model accuracy.
