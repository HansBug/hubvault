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

async function getHeight(locator) {
  const box = await locator.boundingBox();
  expect(box).toBeTruthy();
  return box!.height;
}

async function expectFileKind(page, name, kind) {
  const button = page.getByRole("button", { name: name, exact: true });
  await expect(button).toBeVisible();
  await expect(button).toHaveAttribute("data-file-kind", kind);
}

async function expectFileIconMetrics(page, name, icon, source) {
  const button = page.getByRole("button", { name: name, exact: true });
  await expect(button).toBeVisible();
  const metrics = await button.locator(".table-path__icon").evaluate(function inspectIcon(node) {
    const wrapperRect = node.getBoundingClientRect();
    const glyph = node.querySelector(".table-path__glyph");
    const svg = glyph && glyph.tagName.toLowerCase() === "svg" ? glyph : glyph?.querySelector("svg");
    const glyphRect = glyph ? glyph.getBoundingClientRect() : new DOMRect();
    const svgRect = svg ? svg.getBoundingClientRect() : new DOMRect();
    let bboxWidth = 0;
    let bboxHeight = 0;
    let bboxCenterX = 0;
    let bboxCenterY = 0;
    if (svg) {
      const shapeSelectors = "path,circle,ellipse,rect,polygon,polyline,line,use,image,text";
      const shapes = Array.from(svg.querySelectorAll(shapeSelectors));
      const bounds = shapes
        .map(function measureShape(shape) {
          return shape.getBoundingClientRect();
        })
        .filter(function keepRect(rect) {
          return rect.width > 0 && rect.height > 0;
        });
      if (bounds.length > 0) {
        const left = Math.min.apply(null, bounds.map(function pickLeft(rect) {
          return rect.left;
        }));
        const right = Math.max.apply(null, bounds.map(function pickRight(rect) {
          return rect.right;
        }));
        const top = Math.min.apply(null, bounds.map(function pickTop(rect) {
          return rect.top;
        }));
        const bottom = Math.max.apply(null, bounds.map(function pickBottom(rect) {
          return rect.bottom;
        }));
        bboxWidth = right - left;
        bboxHeight = bottom - top;
        bboxCenterX = left + bboxWidth / 2 - svgRect.left;
        bboxCenterY = top + bboxHeight / 2 - svgRect.top;
      }
    }
    return {
      bboxCenterX: bboxCenterX,
      bboxCenterY: bboxCenterY,
      bboxHeight: bboxHeight,
      bboxWidth: bboxWidth,
      glyphHeight: glyphRect.height,
      glyphWidth: glyphRect.width,
      icon: node.getAttribute("data-file-icon"),
      source: node.getAttribute("data-icon-source"),
      svgHeight: svgRect.height,
      svgWidth: svgRect.width,
      wrapperHeight: wrapperRect.height,
      wrapperWidth: wrapperRect.width
    };
  });
  expect(metrics.icon).toBe(icon);
  expect(metrics.source).toBe(source);
  expect(Math.abs(metrics.wrapperWidth - 30)).toBeLessThan(0.5);
  expect(Math.abs(metrics.wrapperHeight - 30)).toBeLessThan(0.5);
  expect(Math.abs(metrics.glyphWidth - 18)).toBeLessThan(0.5);
  expect(Math.abs(metrics.glyphHeight - 18)).toBeLessThan(0.5);
  expect(Math.abs(metrics.svgWidth - 18)).toBeLessThan(0.5);
  expect(Math.abs(metrics.svgHeight - 18)).toBeLessThan(0.5);
  expect(metrics.bboxWidth).toBeGreaterThan(8);
  expect(metrics.bboxHeight).toBeGreaterThan(8);
  expect(metrics.bboxWidth).toBeLessThanOrEqual(18);
  expect(metrics.bboxHeight).toBeLessThanOrEqual(18);
  expect(Math.abs(metrics.bboxCenterX - 9)).toBeLessThan(2.25);
  expect(Math.abs(metrics.bboxCenterY - 9)).toBeLessThan(2.25);
}

test("readonly frontend supports token query entry plus standalone file and commit pages", async ({ page }) => {
  fs.mkdirSync(screenshotDir, { recursive: true });

  await page.goto("/repo/overview?token=ro-token");

  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByTestId("overview-view")).toBeVisible();
  await expect(page.getByTestId("overview-readme-card")).toContainText("Phase 9 frontend smoke tests");
  await expect(page.getByTestId("overview-readme-card").locator(".token.keyword").first()).toBeVisible();
  await expect(page).not.toHaveURL(/token=/);

  const codeBlockStyles = await page.getByTestId("overview-readme-card").locator("pre code").first().evaluate(async function inspectCode(node) {
    const codeStyle = window.getComputedStyle(node);
    const preStyle = window.getComputedStyle(node.parentElement!);
    const probe = document.createElement("span");
    probe.style.position = "absolute";
    probe.style.visibility = "hidden";
    probe.style.whiteSpace = "pre";
    probe.style.font = codeStyle.font;
    probe.style.fontFamily = codeStyle.fontFamily;
    document.body.appendChild(probe);
    probe.textContent = "中";
    const widthZhA = probe.getBoundingClientRect().width;
    probe.textContent = "文";
    const widthZhB = probe.getBoundingClientRect().width;
    probe.textContent = "M";
    const widthLatin = probe.getBoundingClientRect().width;
    probe.remove();
    return {
      fontFamily: codeStyle.fontFamily,
      color: codeStyle.color,
      backgroundColor: preStyle.backgroundColor,
      widthZhA: widthZhA,
      widthZhB: widthZhB,
      widthLatin: widthLatin,
      sarasaLoaded: document.fonts ? document.fonts.check(codeStyle.fontSize + ' "SarasaMonoCL-Regular"', "中文") : false
    };
  });
  expect(codeBlockStyles.fontFamily).toContain("SarasaMonoCL-Regular");
  expect(codeBlockStyles.sarasaLoaded).toBe(true);
  expect(Math.abs(codeBlockStyles.widthZhA - codeBlockStyles.widthZhB)).toBeLessThan(0.2);
  expect(codeBlockStyles.widthZhA).toBeGreaterThan(codeBlockStyles.widthLatin);
  expect(codeBlockStyles.color).not.toBe(codeBlockStyles.backgroundColor);

  await expect(page.getByTestId("overview-readme-card").locator("table")).toBeVisible();
  await expectImageLoaded(page.getByTestId("overview-readme-card").locator("img").first());
  const readmeLayoutMetrics = await page.getByTestId("overview-readme-card").evaluate(function inspectReadmeCard(node) {
    const markdown = node.querySelector("[data-testid='readme-viewer-markdown']");
    const table = markdown ? markdown.querySelector("table") : null;
    const image = markdown ? markdown.querySelector("img") : null;
    const cardRect = node.getBoundingClientRect();
    const markdownRect = markdown ? markdown.getBoundingClientRect() : new DOMRect();
    const tableRect = table ? table.getBoundingClientRect() : new DOMRect();
    const imageRect = image ? image.getBoundingClientRect() : new DOMRect();
    return {
      cardClientWidth: node.clientWidth,
      cardScrollWidth: node.scrollWidth,
      markdownWidth: markdownRect.width,
      tableWidth: tableRect.width,
      imageWidth: imageRect.width,
      cardWidth: cardRect.width
    };
  });
  expect(readmeLayoutMetrics.cardScrollWidth - readmeLayoutMetrics.cardClientWidth).toBeLessThanOrEqual(4);
  expect(readmeLayoutMetrics.tableWidth).toBeGreaterThan(0);
  expect(readmeLayoutMetrics.tableWidth).toBeLessThanOrEqual(readmeLayoutMetrics.markdownWidth + 1);
  expect(readmeLayoutMetrics.imageWidth).toBeGreaterThan(100);
  expect(readmeLayoutMetrics.imageWidth).toBeLessThanOrEqual(readmeLayoutMetrics.markdownWidth + 1);

  const readmeHeight = await getHeight(page.getByTestId("overview-readme-card"));
  const snapshotHeight = await getHeight(page.getByTestId("overview-snapshot-card"));
  const commitsHeight = await getHeight(page.getByTestId("overview-commits-card"));
  expect(readmeHeight).toBeGreaterThan(snapshotHeight);
  expect(readmeHeight).toBeGreaterThan(commitsHeight);

  const recentCommitButton = page.getByTestId("overview-commits-card").getByRole("button", { name: /update guide model and ui assets/i });
  const recentCommitMetrics = await recentCommitButton.evaluate(function inspectCommitTitle(node) {
    const card = node.closest(".timeline-card");
    const titleText = node.querySelector(".timeline-card__title-text");
    return {
      scrollWidth: card ? card.scrollWidth : 0,
      clientWidth: card ? card.clientWidth : 0,
      titleHeight: titleText ? titleText.getBoundingClientRect().height : 0,
      titleWhiteSpace: titleText ? window.getComputedStyle(titleText).whiteSpace : ""
    };
  });
  expect(recentCommitMetrics.titleWhiteSpace).toBe("normal");
  expect(recentCommitMetrics.scrollWidth - recentCommitMetrics.clientWidth).toBeLessThanOrEqual(4);
  expect(recentCommitMetrics.titleHeight).toBeGreaterThan(28);

  await page.screenshot({
    path: path.join(screenshotDir, "overview.png"),
    fullPage: true
  });

  await recentCommitButton.click();
  await expect(page.getByTestId("commit-detail-view")).toBeVisible();
  await expect(page.getByTestId("commit-detail-view")).toContainText("update guide model and ui assets");
  await page.screenshot({
    path: path.join(screenshotDir, "overview-recent-commit-link.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Storage" }).click();
  await expect(page.getByTestId("storage-view")).toBeVisible();
  await expect(page.getByTestId("storage-status-title")).toHaveText("Quick storage summary ready");
  await expect(page.getByRole("button", { name: "Refresh" })).toBeVisible();
  await expect(page.getByTestId("storage-analysis-strip")).toHaveCount(0);
  await page.screenshot({
    path: path.join(screenshotDir, "storage-initial.png"),
    fullPage: true
  });

  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByTestId("storage-status-title")).toHaveText("Quick storage summary ready");
  await page.getByRole("button", { name: "Load analysis" }).click();
  await expect(page.getByTestId("storage-status-title")).toHaveText("Storage analysis ready");
  await expect(page.getByTestId("storage-analysis-strip")).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDir, "storage.png"),
    fullPage: true
  });

  await page.getByRole("menuitem", { name: "Files" }).click();
  await expect(page.getByTestId("files-view")).toBeVisible();
  await expectFileKind(page, ".gitattributes", "git");
  await expectFileKind(page, "Dockerfile", "docker");

  await page.getByRole("button", { name: "icon-audit", exact: true }).click();
  await expect(page.getByTestId("path-breadcrumb")).not.toContainText("<home>");
  await expect(page.getByRole("button", { name: "Repository root" }).locator(".el-icon")).toBeVisible();
  await expectFileKind(page, "LICENSE", "license");
  await expectFileKind(page, "README.md", "readme");
  await expectFileKind(page, "blob.bin", "binary");
  await expectFileKind(page, "clip.wav", "audio");
  await expectFileKind(page, "demo.mp4", "video");
  await expectFileKind(page, "model.safetensors", "safetensors");
  await expectFileKind(page, "script.py", "python");
  await expectFileIconMetrics(page, "LICENSE", "license", "material");
  await expectFileIconMetrics(page, "README.md", "readme", "material");
  await expectFileIconMetrics(page, "blob.bin", "binary", "element");
  await expectFileIconMetrics(page, "clip.wav", "audio", "element");
  await expectFileIconMetrics(page, "demo.mp4", "video", "element");
  await expectFileIconMetrics(page, "model.safetensors", "huggingface", "material");
  await expectFileIconMetrics(page, "script.py", "python", "material");
  await expectFileIconMetrics(page, "image.png", "image", "material");
  await page.screenshot({
    path: path.join(screenshotDir, "file-icons.png"),
    fullPage: true
  });
  await page.getByRole("button", { name: "Repository root" }).click();

  await page.getByRole("button", { name: "models", exact: true }).click();
  await expectFileKind(page, "model.safetensors", "safetensors");
  await expectFileKind(page, "checkpoint.ckpt", "pytorch");
  await expectFileIconMetrics(page, "model.safetensors", "huggingface", "material");
  await expectFileIconMetrics(page, "checkpoint.ckpt", "pytorch", "material");
  await expectFileKind(page, "network.onnx", "onnx");
  await page.getByRole("button", { name: "Repository root" }).click();

  await page.getByRole("button", { name: "data", exact: true }).click();
  await expectFileKind(page, "train.parquet", "table");
  await expectFileKind(page, "records.jsonl", "table");
  await page.getByRole("button", { name: "Repository root" }).click();

  await page.getByRole("button", { name: "runs", exact: true }).click();
  await expectFileKind(page, "events.out.tfevents.1710000000.fixture", "log");
  await page.getByRole("button", { name: "Repository root" }).click();

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
  fs.mkdirSync(screenshotDir, { recursive: true });

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

  const commitMessageInput = page.getByTestId("upload-commit-message-input");
  await expect(commitMessageInput).toHaveAttribute(
    "placeholder",
    /Upload notes\.txt, second\.txt \(2 files, 24 B\) with hubvault/
  );
  await page.getByRole("button", { name: "Commit Queued Uploads" }).click();

  await expect(page.getByTestId("files-view")).toBeVisible();
  await expect(page.getByTestId("upload-queue-panel")).toHaveCount(0);
  await page.getByRole("button", { name: "notes.txt", exact: true }).click();
  await expect(page.getByTestId("file-detail-view")).toContainText("rw upload");

  await page.getByRole("menuitem", { name: "Commits" }).click();
  await expect(page.getByText(/Upload notes\.txt, second\.txt/)).toBeVisible();

  await page.getByRole("menuitem", { name: "Refs" }).click();
  await expect(page.getByTestId("refs-view")).toBeVisible();
  const refsButtonStyles = await Promise.all([
    "New Branch",
    "New Tag",
    "Merge Into Current",
    "Reset Current",
    "Delete Current"
  ].map(async function collectStyles(label) {
    return page.getByRole("button", { name: label }).evaluate(function inspectButton(node) {
      const style = window.getComputedStyle(node);
      return {
        backgroundColor: style.backgroundColor,
        borderColor: style.borderColor,
        color: style.color
      };
    });
  }));
  expect(refsButtonStyles[0].color).not.toBe(refsButtonStyles[1].color);
  expect(refsButtonStyles[1].color).not.toBe(refsButtonStyles[2].color);
  expect(refsButtonStyles[3].color).not.toBe(refsButtonStyles[4].color);
  await page.screenshot({
    path: path.join(screenshotDir, "refs.png"),
    fullPage: true
  });
});
