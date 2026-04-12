import { describe, expect, it } from "vitest";

import {
  buildBreadcrumbs,
  findReadmePath,
  isCodeLikePath,
  isImagePath,
  isMarkdownPath,
  isTextLikePath,
  naturalCompare,
  sortRepoEntries
} from "@/utils/files";

describe("file helpers", function suite() {
  it("finds the highest-priority readme file", function testFindReadmePath() {
    expect(findReadmePath(["README.txt", "README.md"])).toBe("README.md");
    expect(findReadmePath(["docs/readme.md"])).toBe("");
  });

  it("detects markdown and text-like paths", function testPathKinds() {
    expect(isMarkdownPath("README.md")).toBe(true);
    expect(isImagePath("images/logo.png")).toBe(true);
    expect(isTextLikePath("config.yaml")).toBe(true);
    expect(isCodeLikePath("src/app.py")).toBe(true);
    expect(isCodeLikePath("README.md")).toBe(false);
    expect(isTextLikePath("model.bin")).toBe(false);
  });

  it("builds breadcrumbs for nested paths", function testBreadcrumbs() {
    expect(buildBreadcrumbs("models/core")).toEqual([
      { label: "models", path: "models" },
      { label: "core", path: "models/core" }
    ]);
  });

  it("sorts repository entries like natsort with directories first", function testNaturalSorting() {
    expect(naturalCompare("001alpha.sgi", "01alpha.sgi")).toBeLessThan(0);
    expect(naturalCompare("file2.txt", "file10.txt")).toBeLessThan(0);

    const sorted = sortRepoEntries([
      { path: "docs/file10.txt", entry_type: "file" },
      { path: "docs/section10", entry_type: "folder" },
      { path: "docs/file2.txt", entry_type: "file" },
      { path: "docs/section2", entry_type: "folder" }
    ]);

    expect(sorted.map(function collectPath(item) {
      return item.path;
    })).toEqual([
      "docs/section2",
      "docs/section10",
      "docs/file2.txt",
      "docs/file10.txt"
    ]);
  });
});
