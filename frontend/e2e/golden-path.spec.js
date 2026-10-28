import { expect, test } from "@playwright/test";

test.describe("golden path", () => {
  test("create, run, monitor, and inspect a workflow", async ({ page }) => {
    const workflowName = `E2E pipeline ${Date.now()}`;

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Sign in to DevFlow" })).toBeVisible();
    await page.getByLabel("API key").fill(process.env.DEVFLOW_E2E_API_KEY || "devflow-dev-key");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();

    await page.getByRole("link", { name: "New workflow" }).click();
    await expect(page.getByRole("heading", { name: "Design a workflow" })).toBeVisible();
    await page.getByLabel("Workflow name").fill(workflowName);
    await page.getByLabel("Name", { exact: true }).fill("prepare");
    await page.getByLabel("Duration (ms)").fill("200");
    await page.getByRole("button", { name: "Create workflow" }).click();

    await expect(page.getByRole("heading", { name: "Edit workflow" })).toBeVisible();
    await page.getByRole("button", { name: "Run workflow" }).click();
    await expect(page.getByRole("dialog", { name: "Run this workflow?" })).toBeVisible();
    await page.getByRole("button", { name: "Start run" }).click();

    await expect(page).toHaveURL(/#\/executions\/[\w-]+/);
    await expect(page.getByRole("heading", { name: workflowName })).toBeVisible();
    await expect(page.locator(".page-heading .header-meta .status-pill", { hasText: "Succeeded" })).toBeVisible({
      timeout: 60_000
    });
    await expect(page.getByRole("log")).toBeVisible();
    await expect(page.locator(".log-row", { hasText: "prepare" }).first()).toBeVisible();

    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "Executions" }).click();
    await expect(page.getByRole("heading", { name: "Executions" })).toBeVisible();
    const row = page.getByRole("row", { name: new RegExp(workflowName) });
    await expect(row).toBeVisible();
    await row.getByRole("link").first().click();
    await expect(page.getByRole("heading", { name: workflowName })).toBeVisible();
    await expect(page.getByRole("log")).toBeVisible();
  });
});
