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

test("read-write frontend can upload, mutate refs, and run maintenance actions", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("Paste a read-only or read-write token").fill("rw-token");
  await page.getByRole("button", { name: "Enter Repository" }).click();

  await page.getByRole("menuitem", { name: "Files" }).click();
  await expect(page.getByRole("button", { name: "Upload Files" })).toBeVisible();
  await page.getByTestId("upload-file-input").setInputFiles({
    name: "notes.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("rw upload\n")
  });
  const uploadDialog = page.getByRole("dialog", { name: "Upload to Repository" });
  await expect(uploadDialog).toBeVisible();
  await uploadDialog.getByRole("textbox", { name: "Commit message" }).fill("upload from playwright");
  await uploadDialog.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("notes.txt")).toBeVisible();

  await page.getByRole("button", { name: /notes\.txt/i }).click();
  await page.getByRole("button", { name: "Delete Selected" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete File" });
  await expect(deleteDialog).toBeVisible();
  await deleteDialog.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText("notes.txt")).toHaveCount(0);

  await page.getByRole("menuitem", { name: "Refs" }).click();
  await page.getByRole("button", { name: "New Branch" }).click();
  const createBranchDialog = page.getByRole("dialog", { name: "Create Branch" });
  await expect(createBranchDialog).toBeVisible();
  await createBranchDialog.getByRole("textbox", { name: "Branch name" }).fill("playwright-branch");
  await createBranchDialog.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("button", { name: "playwright-branch" })).toBeVisible();

  await page.getByRole("menuitem", { name: "Storage" }).click();
  await page.getByRole("button", { name: "Preview GC" }).click();
  await expect(page.getByText("Latest GC Result")).toBeVisible();
  await page.getByRole("button", { name: "Squash Current Branch" }).click();
  const squashDialog = page.getByRole("dialog", { name: /Squash / });
  await expect(squashDialog).toBeVisible();
  await squashDialog.getByRole("textbox", { name: "Optional replacement commit message for the new root" }).fill("squash from playwright");
  await squashDialog.getByRole("button", { name: "Squash", exact: true }).click();
  await expect(page.getByText("Latest Squash Result")).toBeVisible();
});
