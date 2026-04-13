import { describe, expect, it } from "vitest";

import {
  buildBreadcrumbs,
  findReadmePath,
  getFileVisualKind,
  isAudioPath,
  isCodeLikePath,
  isImagePath,
  isKnownUnsupportedBrowserVideoPath,
  isMarkdownPath,
  isTextLikePath,
  isVideoPath,
  naturalCompare,
  sortRepoEntries
} from "@/utils/files";

describe("file helpers", function suite() {
  it("finds the highest-priority readme file", function testFindReadmePath() {
    expect(findReadmePath(["README.txt", "README.md"])).toBe("README.md");
    expect(findReadmePath(["docs/readme.md"])).toBe("");
  });

  it("detects markdown, media, code, and text-like paths", function testPathKinds() {
    expect(isMarkdownPath("README.md")).toBe(true);
    expect(isImagePath("images/logo.png")).toBe(true);
    expect(isAudioPath("media/voice.wav")).toBe(true);
    expect(isVideoPath("clips/demo.mp4")).toBe(true);
    expect(isKnownUnsupportedBrowserVideoPath("clips/demo.avi")).toBe(true);
    expect(isKnownUnsupportedBrowserVideoPath("clips/demo.mp4")).toBe(false);
    expect(isTextLikePath("config.yaml")).toBe(true);
    expect(isTextLikePath("requirements-test.txt")).toBe(true);
    expect(isTextLikePath("events.out.tfevents.1710000.fixture")).toBe(false);
    expect(isCodeLikePath("src/app.py")).toBe(true);
    expect(isCodeLikePath("README.md")).toBe(true);
    expect(isCodeLikePath("README.rst")).toBe(false);
    expect(isTextLikePath("model.bin")).toBe(false);
  });

  it("classifies common Hugging Face and GitHub file kinds", function testFileVisualKinds() {
    expect(getFileVisualKind(".gitattributes", "file")).toBe("git");
    expect(getFileVisualKind("README.md", "file")).toBe("readme");
    expect(getFileVisualKind("LICENSE", "file")).toBe("license");
    expect(getFileVisualKind("Dockerfile", "file")).toBe("docker");
    expect(getFileVisualKind("package.json", "file")).toBe("npm");
    expect(getFileVisualKind("pyproject.toml", "file")).toBe("python");
    expect(getFileVisualKind("src/App.tsx", "file")).toBe("react");
    expect(getFileVisualKind("ui/app.vue", "file")).toBe("vue");
    expect(getFileVisualKind("data/train.parquet", "file")).toBe("table");
    expect(getFileVisualKind("data/records.jsonl", "file")).toBe("table");
    expect(getFileVisualKind("reports/run.duckdb", "file")).toBe("database");
    expect(getFileVisualKind("models/model.safetensors", "file")).toBe("safetensors");
    expect(getFileVisualKind("models/checkpoint.ckpt", "file")).toBe("pytorch");
    expect(getFileVisualKind("models/weights.pt", "file")).toBe("pytorch");
    expect(getFileVisualKind("models/network.onnx", "file")).toBe("onnx");
    expect(getFileVisualKind("tensorboard/events.out.tfevents.1710000", "file")).toBe("log");
    expect(getFileVisualKind("notes/README.rst", "file")).toBe("readme");
    expect(getFileVisualKind("weights/model.gguf", "file")).toBe("pytorch");
    expect(getFileVisualKind("archive/release.tar.gz", "file")).toBe("zip");
    expect(getFileVisualKind("fonts/mono.woff2", "file")).toBe("font");
    expect(getFileVisualKind("opaque/payload.bin", "file")).toBe("binary");
    expect(getFileVisualKind("artifacts", "folder")).toBe("folder");
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
