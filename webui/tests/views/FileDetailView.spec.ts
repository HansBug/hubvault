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

    const backButton = wrapper.findAll("button").find(function findMatch(item) {
      return item.text().indexOf("Back to Directory") >= 0;
    });
    expect(backButton).toBeTruthy();
    await backButton!.trigger("click");

    expect(fileDetailMocks.push).toHaveBeenCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });
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
});
