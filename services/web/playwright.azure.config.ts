import { defineConfig } from "@playwright/test";

process.env.PLAYWRIGHT_NO_COPY_PROMPT = "1";

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "azure.spec.ts",
  retries: 0,
  workers: 1,
  reporter: [["./tests/safe-reporter.ts"]],
  timeout: 330000,
  use: { headless: false, trace: "off", screenshot: "off", video: "off" },
});
