# Live beta deployment preparation

Status, 2026-11-09: **not publicly deployed**. The selected scope is real accounts
and the existing protected authentication stack, with no recurring hosting charge.
No cloud account, server, public hostname, SMTP sender or production credentials
have been provisioned. This document records a proposed path, not a tested public
deployment or a production-readiness claim.

## Proposed free hosting path

- **Compute:** an eligible Oracle Cloud Always Free VM, subject to account approval,
  resource limits and regional capacity. Keep the account on its free tier and
  use resources explicitly identified as Always Free; trial credit is temporary
  and is not the same entitlement. Oracle requires card verification and may put
  a temporary authorization hold on the card. The free tier has no uptime SLA.
  See the [official FAQ](https://www.oracle.com/cloud/free/faq/) and
  [resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).
- **Hostname:** a free DuckDNS subdomain, if available, pointed at the VM's public
  address. This does not require buying a domain. See [DuckDNS](https://www.duckdns.org/about.jsp).
- **Public HTTPS:** a TLS terminator such as Caddy, with persistent certificate
  storage and the required DNS/ports. See [automatic HTTPS requirements](https://caddyserver.com/docs/automatic-https).
- **Account email:** a separately approved free transactional SMTP account and
  verified sender. Brevo is a candidate, not an activated integration. Its free
  plan currently allows 300 sends/day; unauthenticated/free-email sender domains
  can be rewritten to a provider-managed address. Actual confirmation and
  recovery delivery must be tested before opening registration. See
  [free-plan limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan)
  and [sender behavior](https://help.brevo.com/hc/en-us/articles/16045394674066-Troubleshooting-Domain-authentication).

Free-tier approval, capacity, sender acceptance and future availability are not
guaranteed. If this combination is unavailable, select another concrete target
and disclose its limits before changing the deployment architecture. Do not
silently remove the account guard or expose a sleeping preview as a dependable
always-on service.

## Application changes still needed after a target exists

The existing Compose files and `tools/free_auth.py` are intentionally local-only.
The gateway has an exact loopback origin and HTTP upstream scheme; the local
operator refuses other realms. Production must have a separate configuration
and new credentials, rather than copying `.env.free-auth.local` or weakening that
operator's checks.

The deployment must run the API, collector, pinned v1 shadow worker, Auth,
PostgREST and PostgreSQL with persistent database storage. Only the HTTPS edge
should expose application traffic; Auth management, raw REST services and the
database must remain private. Configure actual public origins, exact confirmation
and recovery redirects, real SMTP, trusted source headers and verified TLS for
database clients. The rejected v2 candidate remains inactive.

Provision a new realm with the existing migrations and restricted service roles.
Existing local/hosted accounts and records are not automatically migrated, and
public registration must not assign administrator access. Configure retention,
private backups and a restoration procedure appropriate to the beta. Opening a
public app is separate from allowing an administrator to read installation-wide
investigations.

Before publishing the URL, verify an actual confirmation/recovery delivery,
sign-in/session restoration, Member denial at administrator APIs, isolated test
accounts, direct provider cooldown enforcement, collection/scoring health and
restart persistence. Restrict sign-in tests to authorized disposable accounts.
Report what was tested and any remaining limits; a successful landing-page
response alone does not verify these flows.

## Completed preparation checks

- The Docker build context now excludes private `.supabase` state and local
  operational logs, in addition to environment files and generated artifacts.
  An isolated Docker build verified that `.supabase`, `.env`,
  `.env.free-auth.local`, model artifacts and frontend dependencies are absent.
- Frontend Nginx request and request-error logging are disabled because account
  callback URLs contain one-time credentials. An unprivileged, network-isolated
  Nginx syntax check and fictional callback-route smoke test passed. Provider or
  edge logging requires separate review once a hosting target is configured.

These checks changed no running account, model, permission or local database.
They do not establish cloud deployment, SMTP delivery, public HTTPS or uptime.
