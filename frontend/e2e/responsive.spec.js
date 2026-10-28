import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const WIDTHS = [360, 390, 768, 1024, 1440];
const PAGES = [
  { name: "workflows", hash: "#/workflows" },
  { name: "executions", hash: "#/executions" },
  { name: "monitor", hash: "#/monitor" },
  { name: "operations", hash: "#/operations", minWidth: 1024 }
];

const screenshotDir = resolve("../docs/screenshots");

test("core layouts fit every target width without horizontal scroll", async ({ page }) => {
  mkdirSync(screenshotDir, { recursive: true });

  await page.goto("/");
  await page.getByLabel("API key").fill(process.env.DEVFLOW_E2E_API_KEY || "devflow-dev-key");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();

  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 900 });
    for (const target of PAGES) {
      if (target.minWidth && width < target.minWidth) continue;
      await page.goto(`/${target.hash}`);
      await expect(page.locator(".page-stack")).toBeVisible();
      await page.waitForTimeout(600);

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
      if (overflow > 1) {
        const offenders = await page.evaluate(() =>
          [...document.querySelectorAll("*")]
            .filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
            .slice(0, 8)
            .map(
              (element) =>
                `${element.tagName.toLowerCase()}.${String(element.className).replace(/\s+/g, ".")} right=${Math.round(
                  element.getBoundingClientRect().right
                )} width=${Math.round(element.getBoundingClientRect().width)}`
            )
        );
        const metrics = await page.evaluate(() => ({
          innerWidth: window.innerWidth,
          htmlScroll: document.documentElement.scrollWidth,
          bodyScroll: document.body.scrollWidth,
          bodyWidth: Math.round(document.body.getBoundingClientRect().width),
          shellWidth: Math.round(document.querySelector(".app-shell")?.getBoundingClientRect().width || 0),
          mainWidth: Math.round(document.querySelector(".page-stack")?.getBoundingClientRect().width || 0)
        }));
        console.log(`Overflow at ${width}px on ${target.name}:`, metrics, offenders);
      }
      expect(overflow, `${target.name} overflows horizontally at ${width}px`).toBeLessThanOrEqual(1);

      await page.screenshot({ path: `${screenshotDir}/${target.name}-${width}.png`, fullPage: true });
    }
  }
});
