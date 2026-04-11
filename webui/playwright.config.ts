import path from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }]
  ],
  use: {
    baseURL: "http://127.0.0.1:9613",
    trace: "retain-on-failure"
  },
  webServer: {
    command: `bash -lc 'cd "${projectRoot}" && PYTHONPATH=. ./venv/bin/python webui/tests/e2e/serve_fixture.py'`,
    url: "http://127.0.0.1:9613/login",
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
    timeout: 120000
  }
});
