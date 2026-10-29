export const systemFixture = {
  service: "sherlock-logs-api",
  version: "0.1.0",
  status: "ok",
  stage: "foundation",
  checked_at: "2026-10-29T10:00:00Z",
  uptime_seconds: 2,
  integrations: [
    {
      id: "authentication",
      name: "Supabase Auth",
      status: "not_configured",
      detail: "Authentication is not configured.",
    },
    {
      id: "database",
      name: "PostgreSQL",
      status: "not_configured",
      detail: "Event storage is not configured.",
    },
    {
      id: "detector",
      name: "Isolation Forest",
      status: "not_trained",
      detail: "The model is not trained.",
    },
  ],
};
