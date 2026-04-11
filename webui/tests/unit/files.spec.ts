import { describe, expect, it } from "vitest";

import { buildBreadcrumbs, findReadmePath, isMarkdownPath, isTextLikePath } from "@/utils/files";

describe("file helpers", function suite() {
  it("finds the highest-priority readme file", function testFindReadmePath() {
    expect(findReadmePath(["README.txt", "README.md"])).toBe("README.md");
    expect(findReadmePath(["docs/readme.md"])).toBe("");
  });

  it("detects markdown and text-like paths", function testPathKinds() {
    expect(isMarkdownPath("README.md")).toBe(true);
    expect(isTextLikePath("config.yaml")).toBe(true);
    expect(isTextLikePath("model.bin")).toBe(false);
  });

  it("builds breadcrumbs for nested paths", function testBreadcrumbs() {
    expect(buildBreadcrumbs("models/core")).toEqual([
      { label: "models", path: "models" },
      { label: "core", path: "models/core" }
    ]);
  });
});
