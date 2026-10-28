import { existsSync } from "node:fs";
import { resolve } from "node:path";

import { defineConfig, devices } from "@playwright/test";

const backendPort = process.env.DEVFLOW_E2E_BACKEND_PORT || "8010";
const frontendPort = process.env.DEVFLOW_E2E_FRONTEND_PORT || "5175";
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

const repoRoot = resolve("..");
const venvPython = resolve(repoRoot, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
const python = process.env.PYTHON_BIN || (existsSync(venvPython) ? venvPython : "python");

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: frontendUrl,
    trace: "retain-on-failure",
    screenshot: "only-on-failure"
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `${python} -m uvicorn backend.main:app --host 127.0.0.1 --port ${backendPort}`,
      url: `${backendUrl}/health`,
      cwd: "..",
      env: {
        ...process.env,
        DEVFLOW_DATABASE_URL: "sqlite+aiosqlite:///./e2e.devflow.db",
        DEVFLOW_LOG_FORMAT: "text",
        DEVFLOW_WORKER_COUNT: "2",
        DEVFLOW_RATE_LIMIT_REQUESTS_PER_MINUTE: "100000",
        DEVFLOW_RATE_LIMIT_BURST: "10000"
      },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    },
    {
      command: `npm run build && npm run preview -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      url: frontendUrl,
      env: { ...process.env, VITE_PROXY_TARGET: backendUrl },
      reuseExistingServer: !process.env.CI,
      timeout: 120_000
    }
  ]
});
