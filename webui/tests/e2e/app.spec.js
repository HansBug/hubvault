import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const screenshotDir = path.resolve("test-results", "visual");

test("readonly frontend renders overview, files, refs, commits, and storage", async ({ page }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });

  await page.goto("/login");
  await expect(page.getByTestId("login-view")).toBeVisible();

  await page.getByPlaceholder("Paste a read-only or read-write token").fill("ro-token");
  await page.getByRole("button", { name: "Enter Repository" }).click();

  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByTestId("overview-view")).toBeVisible();
  await expect(page.getByTestId("overview-readme-card")).toContainText("HubVault Fixture");
  await page.screenshot({
    path: path.join(screenshotDir, "overview.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Files" }).click();
  await expect(page.getByTestId("files-view")).toBeVisible();
  await page.getByRole("button", { name: /artifacts/i }).click();
  await page.getByRole("button", { name: /model\.bin/i }).click();
  await expect(page.getByTestId("file-preview-panel")).toContainText("model.bin");
  await page.screenshot({
    path: path.join(screenshotDir, "files.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Refs" }).click();
  await expect(page.getByTestId("refs-view")).toBeVisible();
  await page.getByRole("button", { name: "v1.0" }).click();
  await expect(page.getByText("Current: v1.0")).toBeVisible();

  await page.getByRole("menuitem", { name: "Commits" }).click();
  await expect(page.getByTestId("commits-view")).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDir, "commits.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Storage" }).click();
  await expect(page.getByTestId("storage-view")).toBeVisible();
  await expect(page.getByText("Quick Verify")).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDir, "storage.png"),
    fullPage: true
  });
});
