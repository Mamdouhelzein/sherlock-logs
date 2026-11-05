# Per-account brute-force protection

Status, 2026-11-06: the owner chose the free self-hosted route. Its SQL guard, separate Auth stack, gateway, bootstrap and verification suites are implemented; see [free Auth setup and cutover limits](FREE_AUTH.md). Cutover from the existing hosted realm is still pending. The existing hosted project is on Free and disables Password Verification Attempt, requiring Team or Enterprise. No upgrade or hosted Auth configuration change was performed.

## Enforcement boundary

The browser currently signs in directly through Supabase Auth. A counter in React or a password proxy in FastAPI cannot enforce an account limit while the same public Supabase password endpoint remains reachable. CORS does not close that endpoint. The asynchronous failure-log collector also lacks attempted-account identity and is too late to make an authentication decision.

Keep monitoring and ML independent of enforcement. Model outages or synthetic anomaly thresholds must not decide whether someone can sign in.

## Architecture decision

Two routes were assessed. The selected implementation uses self-hosted Supabase Auth with its provider-enforced hook and private account state, preserving the SDK and RLS model. The gateway alone is not the enforcement mechanism.

| Route | Work required | Activation prerequisite |
| --- | --- | --- |
| Keep hosted Supabase Auth | A provider password-verification hook, private atomic account state, authorization tests, and hosted verification. Existing clients, identities, sessions, and profile policies can stay. | A project plan that actually supports the hook. Supabase lists Team/Enterprise, not Free or Pro. Upgrades and purchases require an explicit owner decision. |
| Keep a free software stack | Run a supported authentication service under our control behind a mandatory gateway, with durable account and IP admission limits. Design the issuer, JWT verification, database policies, registration, confirmation, recovery, session migration, email delivery, deployment, and operational recovery together. | A separate architecture decision and a tested migration. Local self-hosting can avoid a hosted subscription but still needs an awake machine; always-on hosting has operating costs. |

The hosted hook is the smaller change to the current application. A gateway placed in front of only Sherlock Logs, while leaving hosted password login available, does not satisfy the second route. Nor should the application replace a mature identity service with an improvised password table.

## Proposed account policy

These are initial development settings to test, not validated production thresholds:

- Count invalid passwords for the same provider account UUID across devices and IPs.
- Use a fixed 15-minute observation window beginning with the first failed attempt.
- On the fifth failure in that window, start a fixed 15-minute password-login cooldown.
- Deny new password logins during the cooldown, including a correct password. Allowing correct guesses immediately would defeat this account gate.
- Attempts during the cooldown do not extend its deadline or increment an unbounded counter.
- At expiry, start fresh on the next attempt. A valid password outside a cooldown clears previous failures.
- Do not revoke existing sessions when a limit is reached. Keep provider confirmation, refresh, and email recovery separate from the password gate.
- Preserve independent provider IP limits; the account gate does not protect nonexistent accounts, broad password spraying, or password-hashing resources by itself.

An attacker who knows an account identifier can deliberately trigger this temporary denial of service. The bounded deadline limits one cooldown's duration but cannot prevent repeated lockouts after expiry. Reliable recovery and an additional bot/IP layer are release requirements. A future verified step-up flow could reduce this tradeoff; the browser must never be allowed to clear state by claiming that a recovery or CAPTCHA succeeded.

## Hosted-hook implementation sequence

1. **Confirm support before applying anything.** Verify the selected project can enable Password Verification Attempt. Keep this work out of the automatic migration path until that architecture is selected.
2. **Create private state.** Plan one row per account with `user_id`, `window_started_at`, a failure count constrained to 0–5, `blocked_until`, and `updated_at`. Reference `auth.users` with account-deletion cleanup. Store UTC timestamps; no password, email, bearer token, or full provider payload.
3. **Make decisions atomic.** Initialize the row safely, then lock it in the same transaction before evaluating the policy. Read the database clock after acquiring the lock. Concurrent requests and multiple Auth instances must see one ordered state transition; no read-then-increment outside a transaction, browser clock, process-local cache, or database sleep.
4. **Restrict execution.** Use a function with a fixed empty search path and explicit schema-qualified objects. Grant the Auth service only the necessary execution/table rights. Enable RLS with narrowly scoped service policies. Deny browser roles, application administrators' user tokens, the event API, collector, and ML worker access to guard state and execution. Do not grant broad database ownership or introduce a service-role key in React.
5. **Validate the hook contract.** Require a valid account UUID and a JSON boolean validity field. Malformed input and storage failures must deny the password request rather than silently permit it. Return a normal provider decision and set `should_logout_user` to boolean `false` on rejection.
6. **Keep public responses generic.** Use the provider's ordinary invalid-credentials response for cooldown denials as well as wrong passwords. Do not expose account existence, counters, remaining guesses, or a special cooldown response to anonymous callers. Keep the form's recovery guidance general. Verify the actual deployed provider version's status, code, and message before relying on equivalence.
7. **Test before activation.** Exercise disposable database state and a local Auth integration, then run a tightly bounded owner-approved hosted check against dedicated test accounts. SQL-only tests do not establish provider transaction persistence or direct-endpoint enforcement.
8. **Activate deliberately.** Apply the reviewed schema and grants, select the SQL hook in the project, and verify direct password requests as well as the React form. Keep a documented owner recovery path if Auth or the hook is unavailable. Do not remove or disable existing protections as an incidental rollback.
9. **Observe without credentials.** Record aggregate gate health and threshold transitions through an authorized server path. Do not label a rejected hook decision as an observed invalid password: a correct password can also be denied during cooldown. Do not feed fabricated invalid-password events into the existing ML collector.

The hook runs after password verification. It can prevent session issuance but does not avoid the cost of password checking. Current upstream Auth code invokes it before the session-issuance transaction and returns the ordinary invalid-credentials response for a rejected decision. Those details must be rechecked against the deployed version; the integration tests must prove failed-attempt state commits even when the overall login fails.

## Acceptance checks

| Check | Required result |
| --- | --- |
| Attempts below threshold | Invalid passwords never issue a session; count advances exactly once per processed hook call. |
| Fifth failure | Cooldown starts at the database time and remains bounded. |
| Correct password during cooldown | No new password session; existing sessions are preserved. |
| Concurrent failures | No lost updates, duplicate state rows, or valid-password bypass after the account is blocked. |
| Change source IP/device | Same account remains subject to its cooldown. |
| Second account | First account's failures do not change the second account's state. |
| Direct provider call | Same policy applies without loading React or using FastAPI. |
| Expired window/cooldown | Fresh accounting begins at the defined boundary, with tests at equality. |
| Successful verification outside cooldown | Failure state is cleared; the provider still checks confirmation and other Auth requirements. |
| Missing account / denied account | Public status, code, message, and observable differences are reviewed for enumeration. No fake account rows are inserted. |
| Unauthenticated/user/admin user token | Cannot read, update, clear, or call guard internals. |
| API/collector/worker login | Cannot modify or execute guard state. |
| Malformed event / database outage / lock timeout | No password-session issuance; safe error without credential or SQL leakage. |
| Recovery and refresh | Normal verified flows remain available without resetting state on an untrusted browser assertion. |
| Restart / multiple processes | Decisions use durable shared state, not a per-process counter. |
| Provider rejection persistence | Recorded failures and cooldown survive separate HTTP requests and failed-login responses. |

No burst against the real development account is authorized by this plan. The earlier permission for exactly two failed sign-ins was used in the separate collection verification and is not reusable.

## Current provider settings inspected

On 2026-11-05 the dashboard showed token endpoint limits of 150 requests per five minutes per IP, verification limits of 30 per five minutes, and signup/sign-in limits of 30 per five minutes. These were read, not changed. Supabase documents token buckets with burst capacity, so a configured rate is not a strict fixed-window account lockout. The token endpoint also handles session refresh and other grants; tightening it requires testing legitimate shared-IP and session traffic.

## Primary references

- [Supabase Auth Hooks and plan availability](https://supabase.com/docs/guides/auth/auth-hooks)
- [Password-verification hook contract and lockout considerations](https://supabase.com/docs/guides/auth/auth-hooks/password-verification-hook)
- [Provider rate limits](https://supabase.com/docs/guides/auth/rate-limits)
- [Supabase Auth password-grant implementation](https://github.com/supabase/auth/blob/master/internal/api/token.go)
- [Supabase CAPTCHA support](https://supabase.com/docs/guides/auth/auth-captcha)
