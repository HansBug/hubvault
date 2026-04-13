import { describe, expect, it, vi } from "vitest";

import {
  buildBreadcrumbs,
  decodeUtf8Bytes,
  findReadmePath,
  getFileVisualKind,
  isAudioPath,
  isCodeLikePath,
  isImagePath,
  isJsonPath,
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
    expect(findReadmePath(null as any)).toBe("");
  });

  it("detects markdown, media, code, and text-like paths", function testPathKinds() {
    expect(isMarkdownPath("README.md")).toBe(true);
    expect(isMarkdownPath("README.rst")).toBe(false);
    expect(isJsonPath("data/config.json")).toBe(true);
    expect(isJsonPath("data/config.yaml")).toBe(false);
    expect(isImagePath("images/logo.png")).toBe(true);
    expect(isAudioPath("media/voice.wav")).toBe(true);
    expect(isVideoPath("clips/demo.mp4")).toBe(true);
    expect(isTextLikePath("README")).toBe(true);
    expect(isTextLikePath("LICENSE")).toBe(true);
    expect(isTextLikePath("CHANGELOG")).toBe(true);
    expect(isTextLikePath("Dockerfile.dev")).toBe(true);
    expect(isTextLikePath("compose.prod.yaml")).toBe(true);
    expect(isTextLikePath("tailwind.config.ts")).toBe(true);
    expect(isTextLikePath("config.yaml")).toBe(true);
    expect(isTextLikePath("requirements-test.txt")).toBe(true);
    expect(isTextLikePath("events.out.tfevents.1710000.fixture")).toBe(false);
    expect(isCodeLikePath("src/app.py")).toBe(true);
    expect(isCodeLikePath("README.md")).toBe(true);
    expect(isCodeLikePath("README.rst")).toBe(false);
    expect(isTextLikePath("model.bin")).toBe(false);
  });

  it("classifies common Hugging Face and GitHub file kinds", function testFileVisualKinds() {
    expect(getFileVisualKind("", "file")).toBe("document");
    expect(getFileVisualKind("README", "file")).toBe("readme");
    expect(getFileVisualKind("LICENSE", "file")).toBe("license");
    expect(getFileVisualKind("CHANGELOG", "file")).toBe("document");
    expect(getFileVisualKind(".gitattributes", "file")).toBe("git");
    expect(getFileVisualKind("Dockerfile", "file")).toBe("docker");
    expect(getFileVisualKind("compose.dev.yaml", "file")).toBe("docker");
    expect(getFileVisualKind("package.json", "file")).toBe("npm");
    expect(getFileVisualKind("pyproject.toml", "file")).toBe("python");
    expect(getFileVisualKind("tailwind.config.ts", "file")).toBe("tailwindcss");
    expect(getFileVisualKind("schema.graphql", "file")).toBe("graphql");
    expect(getFileVisualKind("src/App.tsx", "file")).toBe("react");
    expect(getFileVisualKind("ui/app.vue", "file")).toBe("vue");
    expect(getFileVisualKind("data/train.parquet", "file")).toBe("table");
    expect(getFileVisualKind("data/records.jsonl", "file")).toBe("table");
    expect(getFileVisualKind("reports/run.duckdb", "file")).toBe("database");
    expect(getFileVisualKind("models/model.safetensors", "file")).toBe("pytorch");
    expect(getFileVisualKind("models/checkpoint.ckpt", "file")).toBe("pytorch");
    expect(getFileVisualKind("models/model.bin", "file")).toBe("pytorch");
    expect(getFileVisualKind("models/network.onnx", "file")).toBe("onnx");
    expect(getFileVisualKind("tensorboard/events.out.tfevents.1710000", "file")).toBe("log");
    expect(getFileVisualKind("notes/README.rst", "file")).toBe("readme");
    expect(getFileVisualKind("weights/model.gguf", "file")).toBe("pytorch");
    expect(getFileVisualKind("archive/release.tar.gz", "file")).toBe("zip");
    expect(getFileVisualKind("fonts/mono.woff2", "file")).toBe("font");
    expect(getFileVisualKind("media/screen.svg", "file")).toBe("svg");
    expect(getFileVisualKind("media/sound.mp3", "file")).toBe("audio");
    expect(getFileVisualKind("media/movie.webm", "file")).toBe("video");
    expect(getFileVisualKind("opaque/payload.bin", "file")).toBe("binary");
    expect(getFileVisualKind("artifacts", "folder")).toBe("folder");
  });

  it("builds breadcrumbs for nested paths", function testBreadcrumbs() {
    expect(buildBreadcrumbs("")).toEqual([]);
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

    const duplicated = sortRepoEntries([
      { path: "b/part-2.txt", entry_type: "file" },
      { path: "a/part-2.txt", entry_type: "file" }
    ]);
    expect(duplicated.map(function collectPath(item) {
      return item.path;
    })).toEqual(["a/part-2.txt", "b/part-2.txt"]);
    expect(sortRepoEntries(null as any)).toEqual([]);
  });

  it("decodes utf-8 bytes with and without TextDecoder", function testDecodeUtf8Bytes() {
    const originalTextDecoder = globalThis.TextDecoder;
    const bytes = new Uint8Array([104, 101, 108, 108, 111]);

    expect(decodeUtf8Bytes(bytes)).toBe("hello");

    vi.stubGlobal("TextDecoder", undefined);
    expect(decodeUtf8Bytes(bytes)).toBe("hello");

    vi.stubGlobal("TextDecoder", originalTextDecoder);
  });
});
