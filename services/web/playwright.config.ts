import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "local.spec.ts",
  retries: 0,
  workers: 1,
  reporter: [["./tests/safe-reporter.ts"]],
  use: { baseURL: "http://127.0.0.1:5173", trace: "off", screenshot: "off", video: "off" },
  webServer: { command: "npm run dev -- --port 5173 --strictPort", url: "http://127.0.0.1:5173", reuseExistingServer: false },
});
