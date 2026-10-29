# Frontend

React + TypeScript workspace built with Vite, Tailwind CSS, React Router, TanStack Query, Lucide, and shadcn-style button primitives using Radix Slot.

## Run

From this directory, with Node.js 22.12+ (24 recommended):

```bash
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Start the API using the root README instructions. No Supabase account is required yet.

## Structure

- `src/App.tsx`: overview, architecture, setup, and not-found views.
- `src/lib/api.ts`: runtime API contract validation, timeout, and origin validation.
- `src/components/ui/button.tsx`: reusable accessible button/link styling.
- `src/styles.css`: shared dark green visual tokens and responsive layouts.
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

The development server uses a strict port. Production static hosting must serve index.html for client routes; nginx.conf provides this fallback in the local Compose build. Authentication and administrator routes are future work; current pages contain development status only.
