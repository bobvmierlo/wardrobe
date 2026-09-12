import { defineConfig, devices } from "@playwright/test";

/**
 * One end-to-end test, against the app as it is actually deployed: the built
 * bundle served by FastAPI from a single origin.
 *
 * The unit tests cover the logic that is easy to get wrong, and the backend
 * suite covers every API path. What neither can tell you is whether the React
 * app renders and its buttons are wired to those paths — which is the one thing
 * this is for. So it stays a smoke test: the path somebody walks the first time
 * they use the app. Adding a test per screen here would buy slow, brittle
 * coverage of markup that changes every week.
 */
export default defineConfig({
  testDir: "./e2e",
  // No arbitrary waits anywhere in the specs; these are the only deadlines.
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  use: {
    baseURL: "http://127.0.0.1:8099",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // CI downloads the browser this Playwright version expects. Set
    // PLAYWRIGHT_CHROMIUM_PATH to run against a Chromium that is already on the
    // machine instead — useful in a sandbox that ships one of its own, and the
    // reason this is an override rather than a hard-coded path.
    ...(process.env.PLAYWRIGHT_CHROMIUM_PATH
      ? { launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_PATH } }
      : {}),
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // The app is used on a phone far more than on a desktop, and the layout
    // differs there, so the smoke test runs both.
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "sh ./e2e/serve.sh",
    url: "http://127.0.0.1:8099/api/health",
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
