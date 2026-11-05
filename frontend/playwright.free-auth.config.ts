import { defineConfig, devices } from "@playwright/test";

// Real isolated local Auth, not provider mocks and never the hosted project.
export default defineConfig({
  testDir: "./e2e-free-auth",
  workers: 1,
  retries: 0,
  timeout: 60_000,
  use: { baseURL: "http://127.0.0.1:5180", trace: "off" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    {
      name: "mobile",
      use: { ...devices["iPhone 13"], defaultBrowserType: "chromium" },
    },
  ],
  webServer: [
    {
      command: "../backend/.venv/bin/python ../tools/free_auth.py api",
      url: "http://127.0.0.1:8001/healthz",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "../backend/.venv/bin/python ../tools/free_auth.py frontend",
      url: "http://127.0.0.1:5180",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
