# Frontend

React + TypeScript workspace built with Vite, Tailwind CSS, React Router, TanStack Query, Lucide, and shadcn-style button primitives using Radix Slot.

## Run

From this directory, with Node.js 22.12+ (24 recommended):

```bash
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Start the API using the root README instructions. Public pages work without Supabase; account functionality requires the [Supabase setup](../supabase/README.md).

## Structure

- `src/App.tsx`: overview, architecture, setup, and not-found views.
- `src/auth/`: session provider, sign-in/registration/recovery, protected profiles, and administrator views.
- `src/lib/supabase.ts`: public configuration validation and the official PKCE-enabled Supabase client.
- `src/lib/api.ts`: runtime API contract validation, timeout, and origin validation.
- `src/components/ui/button.tsx`: reusable accessible button/link styling.
- `src/components/CommandMenu.tsx`: keyboard navigation search with a native modal dialog.
- `src/components/SignalVisual.tsx`: explicitly illustrative radar with motion controls.
- `src/styles.css`: charcoal surfaces with blue, violet, amber, and semantic status accents; responsive layouts and reduced-motion support.
- `src/test/`: test setup and synthetic API fixtures.
- `e2e/`: real-API browser integration tests.

The overview shows a manual connection check and its timestamp. An unavailable or malformed API response produces recovery guidance. No synthetic login metrics are presented as live data. Recharts will be added when actual event or evaluation data exists.

## Configuration and checks

Vite loads optional `VITE_API_BASE_URL` from the repository-root `.env`. Its default is http://127.0.0.1:8000. All `VITE_` variables are public at build time; never use that prefix for server credentials.

```bash
npm run lint
npm test
npm run build
# Optional browser integration checks; requires backend setup:
npx playwright install chromium
npm run test:e2e
```

Set `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` in the root `.env` to enable account pages. Only publishable keys are accepted. The same project must be configured in the API. Missing settings disable account forms with setup guidance; there is no development authentication bypass.

Routes include `/login`, `/register`, `/auth/callback`, `/forgot-password`, `/reset-password`, `/account`, and `/admin`. The official client handles PKCE code exchange and session refresh. Browser sessions are only UI state; protected content requires server-verified identity and authorization. Private queries are scoped to the user and cleared on sign-out.

The development server uses a strict port. Production static hosting must serve index.html for client routes; nginx.conf provides this fallback. Browser authentication tests use a second Vite server on port 5174 with test-only public configuration and mocked provider HTTP responses; they do not verify hosted email or project rate limits.
