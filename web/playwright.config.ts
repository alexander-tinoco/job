import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end, against the real stack.
 *
 * Every interface check in this project used to be someone driving a browser by
 * hand and reading the output. These four journeys are the ones where a silent
 * break would not show up in any Python test: the API can be entirely correct
 * while the panel shows nothing.
 *
 * The stack has to be up (`docker compose up -d`) and seeded. Nothing here
 * starts it: a test suite that boots containers hides which failure you are
 * looking at.
 */
export default defineConfig({
  testDir: "./e2e",
  // The suite writes applications, so parallel workers would race on the
  // per-email rate limit and on "you have already applied".
  workers: 1,
  fullyParallel: false,
  // A flake that passes on retry is a flake you never fix.
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
