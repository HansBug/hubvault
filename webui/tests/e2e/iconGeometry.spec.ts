import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { materialFileIcons } from "../../src/icons/materialFileIcons";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMaterialIcon(key: string): string {
  const icon = materialFileIcons[key];
  const width = icon.width || 16;
  const height = icon.height || 16;
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" aria-hidden="true">`,
    icon.body,
    "</svg>"
  ].join("");
}

function collectMaterialIconKeys(): string[] {
  const source = fs.readFileSync(path.resolve("src", "utils", "fileIcons.ts"), "utf8");
  const keys = new Set<string>();
  const pattern = /icon:\s*"([a-z0-9]+)",\s*kind:\s*"[a-z0-9]+",\s*source:\s*"(element|material)"/g;
  let match = pattern.exec(source);
  while (match) {
    if (match[2] === "material") {
      keys.add(match[1]);
    }
    match = pattern.exec(source);
  }
  return Array.from(keys).sort();
}

test("material file icons stay centered within the shared glyph box", async ({ page }) => {
  const materialIcons = collectMaterialIconKeys();
  const screenshotDir = path.resolve("test-results", "visual");

  const html = [
    "<!doctype html>",
    "<html>",
    "<head>",
    '<meta charset="utf-8" />',
    "<style>",
    "body { margin: 0; padding: 24px; font-family: sans-serif; background: #f4fbfc; }",
    ".grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 12px; }",
    ".card { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; background: #ffffff; border: 1px solid rgba(15, 118, 110, 0.08); }",
    ".icon-box { display: inline-flex; width: 30px; height: 30px; flex: none; justify-content: center; align-items: center; border-radius: 10px; background: #eefbfc; }",
    ".glyph { display: inline-flex; width: 18px; height: 18px; align-items: center; justify-content: center; line-height: 0; }",
    ".glyph svg { width: 18px; height: 18px; }",
    ".label { font-size: 12px; color: #0f172a; overflow-wrap: anywhere; }",
    "</style>",
    "</head>",
    "<body>",
    '<div class="grid">',
    materialIcons.map(function renderCard(key) {
      return [
        `<div class="card" data-icon-key="${escapeHtml(key)}">`,
        '<span class="icon-box"><span class="glyph">',
        renderMaterialIcon(key),
        "</span></span>",
        `<span class="label">${escapeHtml(key)}</span>`,
        "</div>"
      ].join("");
    }).join(""),
    "</div>",
    "</body>",
    "</html>"
  ].join("");

  await page.setContent(html);
  fs.mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDir, "material-icons-grid.png"),
    fullPage: true
  });

  const metrics = await page.locator("[data-icon-key]").evaluateAll(function inspectIcons(nodes) {
    return nodes.map(function buildMetrics(node) {
      const key = node.getAttribute("data-icon-key") || "";
      const iconBox = node.querySelector(".icon-box");
      const glyph = node.querySelector(".glyph");
      const svg = node.querySelector("svg");
      const boxRect = iconBox ? iconBox.getBoundingClientRect() : new DOMRect();
      const glyphRect = glyph ? glyph.getBoundingClientRect() : new DOMRect();
      const svgRect = svg ? svg.getBoundingClientRect() : new DOMRect();
      let bboxWidth = 0;
      let bboxHeight = 0;
      let bboxCenterX = 0;
      let bboxCenterY = 0;
      if (svg) {
        const shapeSelectors = "path,circle,ellipse,rect,polygon,polyline,line,use,image,text";
        const bounds = Array.from(svg.querySelectorAll(shapeSelectors))
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
        glyphHeight: glyphRect.height,
        glyphWidth: glyphRect.width,
        key: key,
        shapeCount: svg ? svg.querySelectorAll("path,circle,ellipse,rect,polygon,polyline,line,use,image,text").length : 0,
        svgHeight: svgRect.height,
        svgWidth: svgRect.width,
        wrapperHeight: boxRect.height,
        wrapperWidth: boxRect.width
      };
    });
  });

  const failures = metrics.filter(function pickFailure(metric) {
    return (
      Math.abs(metric.wrapperWidth - 30) >= 0.5 ||
      Math.abs(metric.wrapperHeight - 30) >= 0.5 ||
      Math.abs(metric.glyphWidth - 18) >= 0.5 ||
      Math.abs(metric.glyphHeight - 18) >= 0.5 ||
      Math.abs(metric.svgWidth - 18) >= 0.5 ||
      Math.abs(metric.svgHeight - 18) >= 0.5 ||
      metric.shapeCount <= 0
    );
  });

  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});
