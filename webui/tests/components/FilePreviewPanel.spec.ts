import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import FilePreviewPanel from "@/components/FilePreviewPanel.vue";

describe("FilePreviewPanel", function suite() {
  it("renders metadata and text preview for readable files", function testPreviewPanel() {
    const wrapper = mount(FilePreviewPanel, {
      props: {
        entry: {
          entry_type: "file",
          path: "README.md",
          size: 12,
          last_commit: {
            oid: "1234567890abcdef",
            title: "seed repo",
            date: "2026-04-11T12:00:00"
          }
        },
        content: "# Demo",
        previewMode: "markdown",
        revision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("seed repo");
    expect(wrapper.text()).toContain("README.md");
    expect(wrapper.find("a").attributes("href")).toContain("/api/v1/content/download/README.md");
  });

  it("covers folder metadata, loading placeholders, binary fallback, and generic empty states", function testOtherPreviewModes() {
    const folderWrapper = mount(FilePreviewPanel, {
      props: {
        entry: {
          entry_type: "folder",
          path: "docs",
          last_commit: null
        },
        previewMode: "binary",
        revision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(folderWrapper.text()).toContain("docs");
    expect(folderWrapper.text()).toContain("Unknown");
    expect(folderWrapper.text()).toContain("This file is treated as binary or too large for inline preview.");
    expect(folderWrapper.find("a").exists()).toBe(false);

    const loadingWrapper = mount(FilePreviewPanel, {
      props: {
        entry: null,
        loading: true,
        previewMode: "empty"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(loadingWrapper.html()).toContain("el-skeleton");
    expect(loadingWrapper.text()).toContain("Select a file from the table to preview its content.");

    const textWrapper = mount(FilePreviewPanel, {
      props: {
        entry: {
          entry_type: "file",
          path: "docs/data.json",
          size: 16,
          last_commit: {
            oid: "abcdef1234567890",
            title: "update data",
            date: "2026-04-12T00:00:00"
          }
        },
        content: "{\"demo\": true}",
        previewMode: "json",
        revision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(textWrapper.text()).toContain("{\"demo\": true}");

    const emptyWrapper = mount(FilePreviewPanel, {
      props: {
        entry: null,
        previewMode: "empty"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(emptyWrapper.text()).toContain("Select a text-like file to preview, or download binary content directly.");
  });
});
