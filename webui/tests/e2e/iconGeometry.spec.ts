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
  const left = icon.left || 0;
  const top = icon.top || 0;
  const width = icon.width || 16;
  const height = icon.height || 16;
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${left} ${top} ${width} ${height}" aria-hidden="true">`,
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
      const viewBox = svg ? svg.viewBox.baseVal : { x: 0, y: 0, width: 0, height: 0 };
      const topLevelGraphics = svg
        ? Array.from(svg.children)
            .filter(function pickGraphicChild(child) {
              const tagName = child.tagName.toLowerCase();
              return tagName !== "defs" && tagName !== "desc" && tagName !== "title" && typeof child.getBBox === "function";
            })
            .map(function measureGraphicChild(child) {
              try {
                const bbox = child.getBBox();
                return {
                  tagName: child.tagName.toLowerCase(),
                  x: bbox.x,
                  y: bbox.y,
                  width: bbox.width,
                  height: bbox.height
                };
              } catch (_error) {
                return null;
              }
            })
            .filter(function keepGraphicChild(item) {
              return item && item.width > 0 && item.height > 0;
            })
        : [];
      const visibleBounds = svg
        ? Array.from(svg.querySelectorAll("path,circle,ellipse,rect,polygon,polyline,line,use,image,text"))
            .map(function measureVisibleShape(shape) {
              const fill = shape.getAttribute("fill");
              const stroke = shape.getAttribute("stroke");
              const style = window.getComputedStyle(shape);
              const hasPaint = !(
                (fill === "none" || style.fill === "none") &&
                (!stroke || stroke === "none" || style.stroke === "none")
              );
              if (!hasPaint) {
                return null;
              }
              if (typeof shape.getBBox !== "function") {
                return null;
              }
              try {
                const bbox = shape.getBBox();
                return bbox.width > 0 && bbox.height > 0
                  ? { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height }
                  : null;
              } catch (_error) {
                return null;
              }
            })
            .filter(function keepVisibleShape(item) {
              return Boolean(item);
            })
            .reduce(function mergeVisibleBounds(acc, item) {
              if (!acc) {
                return {
                  x1: item.x,
                  y1: item.y,
                  x2: item.x + item.width,
                  y2: item.y + item.height
                };
              }
              return {
                x1: Math.min(acc.x1, item.x),
                y1: Math.min(acc.y1, item.y),
                x2: Math.max(acc.x2, item.x + item.width),
                y2: Math.max(acc.y2, item.y + item.height)
              };
            }, null)
        : null;
      const scale = viewBox.width > 0 && viewBox.height > 0 ? Math.min(svgRect.width / viewBox.width, svgRect.height / viewBox.height) : 0;
      const offsetX = (svgRect.width - viewBox.width * scale) / 2;
      const offsetY = (svgRect.height - viewBox.height * scale) / 2;
      const overflowingChildren = topLevelGraphics.filter(function pickOverflow(item) {
        return (
          item.x < viewBox.x - 0.01 ||
          item.y < viewBox.y - 0.01 ||
          item.x + item.width > viewBox.x + viewBox.width + 0.01 ||
          item.y + item.height > viewBox.y + viewBox.height + 0.01
        );
      });
      return {
        glyphHeight: glyphRect.height,
        glyphWidth: glyphRect.width,
        key: key,
        paintedCenterX: visibleBounds
          ? offsetX + (visibleBounds.x1 + (visibleBounds.x2 - visibleBounds.x1) / 2 - viewBox.x) * scale
          : 0,
        paintedCenterY: visibleBounds
          ? offsetY + (visibleBounds.y1 + (visibleBounds.y2 - visibleBounds.y1) / 2 - viewBox.y) * scale
          : 0,
        paintedHeight: visibleBounds ? (visibleBounds.y2 - visibleBounds.y1) * scale : 0,
        paintedMaxDimension: visibleBounds
          ? Math.max((visibleBounds.x2 - visibleBounds.x1) * scale, (visibleBounds.y2 - visibleBounds.y1) * scale)
          : 0,
        paintedWidth: visibleBounds ? (visibleBounds.x2 - visibleBounds.x1) * scale : 0,
        overflowingChildren: overflowingChildren,
        shapeCount: svg ? svg.querySelectorAll("path,circle,ellipse,rect,polygon,polyline,line,use,image,text").length : 0,
        svgHeight: svgRect.height,
        svgWidth: svgRect.width,
        viewBoxHeight: viewBox.height,
        viewBoxWidth: viewBox.width,
        viewBoxX: viewBox.x,
        viewBoxY: viewBox.y,
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
      metric.shapeCount <= 0 ||
      metric.paintedMaxDimension < 13.25 ||
      Math.abs(metric.paintedCenterX - 9) > 1.75 ||
      Math.abs(metric.paintedCenterY - 9) > 1.75 ||
      metric.overflowingChildren.length > 0
    );
  });

  expect(failures, JSON.stringify(failures, null, 2)).toEqual([]);
});
