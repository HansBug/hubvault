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

  it("keeps readme and license files on dedicated documentation icons", function testDocsIconSources() {
    expect(getFileIconMeta("README.md", "file")).toMatchObject({
      icon: "readme",
      kind: "readme",
      source: "material"
    });
    expect(getFileIconMeta("LICENSE", "file")).toMatchObject({
      icon: "license",
      kind: "license",
      source: "material"
    });
  });

  it("maps safetensors to a Hugging Face branded icon instead of PyTorch", function testSafetensorsIconSource() {
    expect(getFileIconMeta("models/model.safetensors", "file")).toMatchObject({
      icon: "huggingface",
      kind: "safetensors",
      source: "material"
    });
    expect(getFileIconMeta("models/model.pt", "file")).toMatchObject({
      icon: "pytorch",
      kind: "pytorch",
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

  it("exports explicit viewBox dimensions for every bundled material icon", function testMaterialIconBounds() {
    const invalid = Object.entries(materialFileIcons)
      .filter(function pickInvalidIcon([_key, icon]) {
        return typeof icon.width !== "number" || typeof icon.height !== "number" || icon.width <= 0 || icon.height <= 0;
      })
      .map(function collectInvalidKey([key]) {
        return key;
      });

    expect(invalid).toEqual([]);
    expect(materialFileIcons.readme).toMatchObject({ width: 24, height: 24 });
    expect(materialFileIcons.pytorch).toMatchObject({ width: 24, height: 24 });
    expect(materialFileIcons.huggingface).toMatchObject({ width: 95, height: 88 });
  });
});
