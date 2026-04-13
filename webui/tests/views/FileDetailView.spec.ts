import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const fileDetailMocks = vi.hoisted(function buildFileDetailMocks() {
  return {
    route: {
      params: {
        pathMatch: ["docs", "guide.md"]
      }
    },
    push: vi.fn(),
    getBlobBytes: vi.fn(),
    getPathsInfo: vi.fn()
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRoute: function useRoute() {
      return fileDetailMocks.route;
    },
    useRouter: function useRouter() {
      return {
        push: fileDetailMocks.push
      };
    }
  };
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    buildBlobUrl: vi.fn(function buildBlobUrl(revision, path) {
      return "/api/v1/content/blob/" + path + "?revision=" + revision;
    }),
    buildDownloadUrl: vi.fn(function buildDownloadUrl(revision, path) {
      return "/api/v1/content/download/" + path + "?revision=" + revision;
    }),
    getBlobBytes: fileDetailMocks.getBlobBytes,
    getPathsInfo: fileDetailMocks.getPathsInfo
  };
});

vi.mock("@/components/CodeViewer.vue", function mockCodeViewer() {
  return {
    default: {
      props: ["content", "path"],
      template: "<div data-testid=\"code-viewer-stub\">{{ path }}|{{ content }}</div>"
    }
  };
});

vi.mock("@/components/ReadmeViewer.vue", function mockReadmeViewer() {
  return {
    default: {
      props: ["content", "path"],
      template: "<div data-testid=\"readme-viewer-stub\">{{ path }}|{{ content }}</div>"
    }
  };
});

import FileDetailView from "@/views/FileDetailView.vue";

function findButtonByLabelOrText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(value) >= 0 || item.attributes("aria-label") === value;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("FileDetailView", function suite() {
  beforeEach(function resetFileDetailMocks() {
    vi.clearAllMocks();
    fileDetailMocks.route.params.pathMatch = ["docs", "guide.md"];
    fileDetailMocks.getPathsInfo.mockResolvedValue([
      {
        path: "docs/guide.md",
        entry_type: "file",
        size: 16,
        oid: "oid-1",
        sha256: "sha-1",
        blob_id: "blob-1",
        etag: "etag-1",
        last_commit: {
          oid: "commit-guide",
          title: "update guide",
          date: "2026-04-12T00:00:00Z"
        }
      }
    ]);
    fileDetailMocks.getBlobBytes.mockResolvedValue(new TextEncoder().encode("# Guide\n\nHello\n").buffer);
  });

  it("loads markdown files and navigates back to the current directory", async function testMarkdownDetail() {
    const wrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(fileDetailMocks.getPathsInfo).toHaveBeenCalledWith("release/v1", ["docs/guide.md"]);
    expect(fileDetailMocks.getBlobBytes).toHaveBeenCalledWith("release/v1", "docs/guide.md");
    expect(wrapper.get("[data-testid='readme-viewer-stub']").text()).toContain("docs/guide.md|# Guide");
    expect(wrapper.text()).not.toContain("<home>");
    expect(wrapper.get("[data-testid='path-breadcrumb']").text()).toContain("docs");
    expect(wrapper.findAll("button").some(function hasRepositoryRoot(item) {
      return item.attributes("aria-label") === "Repository root";
    })).toBe(true);

    await findButtonByLabelOrText(wrapper, "Back to Directory").trigger("click");

    expect(fileDetailMocks.push).toHaveBeenCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });
  });

  it("opens the last commit directly from the file metadata card", async function testOpenLastCommit() {
    const wrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await findButtonByLabelOrText(wrapper, "update guide").trigger("click");

    expect(fileDetailMocks.push).toHaveBeenCalledWith({
      name: "commit-detail",
      params: {
        commitId: "commit-guide"
      },
      query: {
        revision: "release/v1"
      }
    });
  });

  it("renders audio previews without fetching text bytes", async function testAudioDetail() {
    fileDetailMocks.route.params.pathMatch = ["media", "intro.wav"];
    fileDetailMocks.getPathsInfo.mockResolvedValue([
      {
        path: "media/intro.wav",
        entry_type: "file",
        size: 2048,
        oid: "oid-3",
        sha256: "sha-3",
        blob_id: "blob-3",
        etag: "etag-3",
        last_commit: null
      }
    ]);

    const wrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(fileDetailMocks.getBlobBytes).not.toHaveBeenCalled();
    expect(wrapper.get("audio").attributes("src")).toContain("/api/v1/content/blob/media/intro.wav?revision=release/v1");
  });

  it("renders image previews without fetching text bytes", async function testImageDetail() {
    fileDetailMocks.route.params.pathMatch = ["images", "logo.png"];
    fileDetailMocks.getPathsInfo.mockResolvedValue([
      {
        path: "images/logo.png",
        entry_type: "file",
        size: 128,
        oid: "oid-2",
        sha256: "sha-2",
        blob_id: "blob-2",
        etag: "etag-2",
        last_commit: null
      }
    ]);

    const wrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(fileDetailMocks.getBlobBytes).not.toHaveBeenCalled();
    expect(wrapper.get("img").attributes("src")).toContain("/api/v1/content/blob/images/logo.png?revision=release/v1");
  });

  it("shows an inline fallback for avi files instead of a broken video player", async function testUnsupportedVideoDetail() {
    fileDetailMocks.route.params.pathMatch = ["media", "demo.avi"];
    fileDetailMocks.getPathsInfo.mockResolvedValue([
      {
        path: "media/demo.avi",
        entry_type: "file",
        size: 2048,
        oid: "oid-4",
        sha256: "sha-4",
        blob_id: "blob-4",
        etag: "etag-4",
        last_commit: null
      }
    ]);

    const wrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(fileDetailMocks.getBlobBytes).not.toHaveBeenCalled();
    expect(wrapper.find("video").exists()).toBe(false);
    expect(wrapper.get("[data-testid='media-preview-unavailable']").text()).toContain(
      "AVI video preview is not available in this browser."
    );
    expect(wrapper.get("[data-testid='media-preview-download']").attributes("href")).toContain(
      "/api/v1/content/download/media/demo.avi?revision=release/v1"
    );
  });

  it("formats json previews and falls back to the raw payload when the json is invalid", async function testJsonPreviewBranches() {
    fileDetailMocks.route.params.pathMatch = ["data", "config.json"];
    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([
      {
        path: "data/config.json",
        entry_type: "file",
        size: 18,
        oid: "oid-json",
        sha256: "sha-json",
        blob_id: "blob-json",
        etag: "etag-json",
        last_commit: {
          oid: "",
          title: "",
          date: ""
        }
      }
    ]);
    fileDetailMocks.getBlobBytes.mockResolvedValueOnce(new TextEncoder().encode("{\"value\":1}").buffer);

    const formattedWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(formattedWrapper.get("[data-testid='code-viewer-stub']").text()).toContain("{\n  \"value\": 1\n}");
    expect(formattedWrapper.find(".detail-commit-link").exists()).toBe(false);

    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([
      {
        path: "data/config.json",
        entry_type: "file",
        size: 18,
        oid: "oid-json-raw",
        sha256: "sha-json-raw",
        blob_id: "blob-json-raw",
        etag: "etag-json-raw",
        last_commit: null
      }
    ]);
    fileDetailMocks.getBlobBytes.mockResolvedValueOnce(new TextEncoder().encode("{not json").buffer);

    const rawWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(rawWrapper.get("[data-testid='code-viewer-stub']").text()).toContain("{not json");
  });

  it("keeps root-level files query-free when navigating back and shortens untitled commit links", async function testRootBackNavigation() {
    fileDetailMocks.route.params.pathMatch = ["README.md"];
    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([
      {
        path: "README.md",
        entry_type: "file",
        size: 16,
        oid: "oid-root",
        sha256: "sha-root",
        blob_id: "blob-root",
        etag: "etag-root",
        last_commit: {
          oid: "1234567890abcdef",
          title: "",
          date: "2026-04-12T00:00:00Z"
        }
      }
    ]);
    fileDetailMocks.getBlobBytes.mockResolvedValueOnce(new TextEncoder().encode("# Root\n").buffer);

    const wrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(wrapper.text()).toContain("12345678");

    await findButtonByLabelOrText(wrapper, "Back to Directory").trigger("click");

    expect(fileDetailMocks.push).toHaveBeenCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: undefined
      }
    });
  });

  it("renders binary and video previews without fetching text bytes", async function testBinaryAndVideoBranches() {
    fileDetailMocks.route.params.pathMatch = "artifacts/model.bin" as any;
    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([
      {
        path: "artifacts/model.bin",
        entry_type: "file",
        size: 2 * 1024 * 1024,
        oid: "oid-bin",
        sha256: "sha-bin",
        blob_id: "blob-bin",
        etag: "etag-bin",
        last_commit: null
      }
    ]);

    const binaryWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(fileDetailMocks.getBlobBytes).not.toHaveBeenCalled();
    expect(binaryWrapper.text()).toContain("This binary file cannot be rendered inline.");

    await findButtonByLabelOrText(binaryWrapper, "Back to Directory").trigger("click");
    expect(fileDetailMocks.push).toHaveBeenCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "artifacts"
      }
    });

    fileDetailMocks.route.params.pathMatch = ["media", "demo.mp4"];
    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([
      {
        path: "media/demo.mp4",
        entry_type: "file",
        size: 2048,
        oid: "oid-video",
        sha256: "sha-video",
        blob_id: "blob-video",
        etag: "etag-video",
        last_commit: null
      }
    ]);

    const videoWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(videoWrapper.get("video").attributes("src")).toContain("/api/v1/content/blob/media/demo.mp4?revision=release/v1");
  });

  it("handles missing paths and unreadable file metadata gracefully", async function testDetailErrors() {
    fileDetailMocks.route.params.pathMatch = undefined as any;

    const missingWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(fileDetailMocks.getPathsInfo).not.toHaveBeenCalled();
    expect(missingWrapper.find("a[href]").exists()).toBe(false);
    expect((missingWrapper.vm as any).blobUrl).toBe("");

    fileDetailMocks.route.params.pathMatch = ["docs", "folder"];
    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([
      {
        path: "docs/folder",
        entry_type: "folder"
      }
    ]);

    const nonFileWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(nonFileWrapper.text()).toContain("Selected path is not a file.");

    fileDetailMocks.route.params.pathMatch = ["docs", "missing.txt"];
    fileDetailMocks.getPathsInfo.mockResolvedValueOnce([]);

    const missingEntryWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(missingEntryWrapper.text()).toContain("Selected path is not a file.");

    fileDetailMocks.route.params.pathMatch = ["docs", "broken.txt"];
    fileDetailMocks.getPathsInfo.mockRejectedValueOnce({});

    const errorWrapper = mount(FileDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(errorWrapper.text()).toContain("Unable to load file detail.");
  });
});
