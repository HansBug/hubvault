import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const screenshotDir = path.resolve("test-results", "visual");

async function expectImageLoaded(locator) {
  await expect(locator).toBeVisible();
  const metrics = await locator.evaluate(function inspectImage(node) {
    return {
      complete: node.complete,
      naturalWidth: node.naturalWidth,
      naturalHeight: node.naturalHeight
    };
  });
  expect(metrics.complete).toBe(true);
  expect(metrics.naturalWidth).toBeGreaterThan(100);
  expect(metrics.naturalHeight).toBeGreaterThan(100);
}

test("readonly frontend supports token query entry plus standalone file and commit pages", async ({ page }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });

  await page.goto("/repo/overview?token=ro-token");

  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByTestId("overview-view")).toBeVisible();
  await expect(page.getByTestId("overview-readme-card")).toContainText("Phase 9 frontend smoke tests");
  await expect(page).not.toHaveURL(/token=/);
  await page.screenshot({
    path: path.join(screenshotDir, "overview.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Files" }).click();
  await expect(page.getByTestId("files-view")).toBeVisible();
  await page.getByRole("button", { name: "src", exact: true }).click();
  await page.getByRole("button", { name: "app.py", exact: true }).click();
  await expect(page.getByTestId("file-detail-view")).toBeVisible();
  await expect(page.getByTestId("code-viewer")).toContainText("fixture v2");
  await expect(page.locator(".line-numbers-rows")).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDir, "file-code.png"),
    fullPage: true
  });

  await page.getByRole("button", { name: "Back to Directory" }).click();
  await page.getByRole("button", { name: "Repository root" }).click();
  await page.getByRole("button", { name: "images", exact: true }).click();
  await page.getByRole("button", { name: "logo.svg", exact: true }).click();
  await expectImageLoaded(page.getByTestId("file-detail-view").locator("img"));
  await page.screenshot({
    path: path.join(screenshotDir, "file-image.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Commits" }).click();
  await expect(page.getByTestId("commits-view")).toBeVisible();
  await page.getByRole("button", { name: /update guide model and ui assets/i }).first().click();
  await expect(page.getByTestId("commit-detail-view")).toBeVisible();
  await expect(page.getByTestId("html-diff-viewer").first()).toBeVisible();
  await expect(page.getByTestId("image-compare-viewer")).toBeVisible();
  await expect.poll(async function countCompareImages() {
    return page.getByTestId("image-compare-viewer").locator("img").count();
  }).toBeGreaterThanOrEqual(2);
  const compareImages = await page.getByTestId("image-compare-viewer").locator("img").evaluateAll(function collect(nodes) {
    return nodes.map(function buildState(node) {
      return {
        complete: node.complete,
        naturalWidth: node.naturalWidth,
        naturalHeight: node.naturalHeight
      };
    });
  });
  expect(compareImages.length).toBeGreaterThanOrEqual(2);
  compareImages.forEach(function assertLoaded(state) {
    expect(state.complete).toBe(true);
    expect(state.naturalWidth).toBeGreaterThan(100);
    expect(state.naturalHeight).toBeGreaterThan(100);
  });
  await page.screenshot({
    path: path.join(screenshotDir, "commit-detail.png"),
    fullPage: true
  });
});

test("read-write frontend queues multiple uploads and commits them in one batch", async ({ page }) => {
  await page.goto("/repo/files?revision=release%2Fv1&token=rw-token");

  await expect(page.getByTestId("files-view")).toBeVisible();
  await page.getByTestId("files-upload-button").click();
  await expect(page.getByTestId("upload-view")).toBeVisible();
  await expect(page.getByTestId("upload-queue-panel")).toBeVisible();

  await page.getByTestId("upload-file-input").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("rw upload\n")
  });
  await page.getByTestId("upload-file-input").setInputFiles({
    name: "second.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("second upload\n")
  });

  await expect(page.getByText("notes.txt")).toBeVisible();
  await expect(page.getByText("second.txt")).toBeVisible();

  await page.getByPlaceholder("Commit message for the queued upload batch").fill("upload from playwright");
  await page.getByRole("button", { name: "Commit Queued Uploads" }).click();

  await expect(page.getByTestId("files-view")).toBeVisible();
  await expect(page.getByTestId("upload-queue-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "notes.txt", exact: true }).click();
  await expect(page.getByTestId("file-detail-view")).toContainText("rw upload");
});
