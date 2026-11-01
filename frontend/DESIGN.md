# Sherlock Logs visual direction

Use the requested Anthropic frontend-design skill to make a practical security investigation workspace with a distinct visual identity. Keep the existing React, FastAPI, Supabase, and permission boundaries.

## Plan

Palette: mist `#F0F3F8`, paper `#FFFFFF`, ink `#17243C`, cobalt `#2859CF`, iris `#7964B1`, ochre `#A56B17`. Cobalt identifies actions; violet identifies storage/context; amber identifies pending work. Green is reserved for a verified healthy connection.

Typography: self-hosted IBM Plex Sans, variable weights 400–700. Use a 16px body, a 1.5–1.65 reading line height, and a deliberate 48–64px display scale. Monospace is reserved for actual code and measured values. Headings and labels use sentence case.

Two layout studies:

```text
A: navigation rail | headline + event trail
                   | connection | ordered setup progress
                   | integration rows

B: top navigation
   centered headline
   three equal status cards
```

Choose A. Left-align content and use an asymmetric split for the introductory area. The event trail is the one signature element: a diagram of observed fact → private record → future review, explicitly labeled as a workflow rather than live activity. Make connection checks prominent; preserve clear empty, error, loading, and untrained states. Account forms use a quiet white surface and ordinary labels.

## Review before implementation

Study B repeats the familiar SaaS card template. Study A fits the work: navigation stays available while a record is inspected, service checks form a compact console, and integrations are compared in rows. Remove the radar, gradient washes, glowing badges, decorative section numbers, tracked uppercase labels, and ambient-effects control. Retain chronological numbering only for an actual ordered process. Keep violet and amber as meaningful secondary colors, honoring the user's preference for more than green.

## Implementation checks

Use visible keyboard focus, 44px interactive targets, responsive layouts down to 320px, and reduced-motion support. Keep page search and route access intact. Never fabricate events, model scores, detections, or readiness from configuration alone. Verify desktop and mobile screenshots, real API states, and authentication regressions before delivery.
