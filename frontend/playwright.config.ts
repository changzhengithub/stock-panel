import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8011",
    ...devices["Desktop Chrome"],
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 1440, height: 1100 },
    screenshot: "only-on-failure",
  },
  webServer: {
    command: "../backend/.venv/bin/python ../backend/tests/e2e_server.py",
    url: "http://127.0.0.1:8011/api/data-status",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
