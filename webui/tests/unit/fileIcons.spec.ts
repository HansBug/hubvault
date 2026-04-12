import { describe, expect, it } from "vitest";

import { materialFileIcons } from "@/icons/materialFileIcons";
import { FILE_ICON_META, getFileIconMeta } from "@/utils/fileIcons";

describe("file icon metadata", function suite() {
  it("uses aligned element icons for media types with known material outliers", function testMediaIconSources() {
    expect(getFileIconMeta("media/clip.wav", "file")).toMatchObject({
      icon: "audio",
      kind: "audio",
      source: "element"
    });
    expect(getFileIconMeta("media/demo.mp4", "file")).toMatchObject({
      icon: "video",
      kind: "video",
      source: "element"
    });
  });

  it("keeps python files on a dedicated material icon", function testPythonIconSource() {
    expect(getFileIconMeta("src/app.py", "file")).toMatchObject({
      icon: "python",
      kind: "python",
      source: "material"
    });
  });

  it("has bundled SVG data for every material icon metadata entry", function testMaterialIconCoverage() {
    const missing = Object.values(FILE_ICON_META)
      .filter(function pickMaterialMeta(meta) {
        return meta.source === "material";
      })
      .filter(function pickMissing(meta) {
        return !materialFileIcons[meta.icon];
      })
      .map(function collectIcon(meta) {
        return meta.icon;
      });

    expect(missing).toEqual([]);
  });
});
