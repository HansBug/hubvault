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
});
