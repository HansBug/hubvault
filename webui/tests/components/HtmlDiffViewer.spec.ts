import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import HtmlDiffViewer from "@/components/HtmlDiffViewer.vue";

describe("HtmlDiffViewer", function suite() {
  it("renders diff2html output for unified diffs", function testHtmlDiffViewer() {
    const wrapper = mount(HtmlDiffViewer, {
      props: {
        diffText: [
          "diff --git a/demo.txt b/demo.txt",
          "--- a/demo.txt",
          "+++ b/demo.txt",
          "@@ -1 +1 @@",
          "-old",
          "+new"
        ].join("\n")
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.get("[data-testid='html-diff-viewer']").html()).toContain("d2h-wrapper");
    expect(wrapper.get("[data-testid='html-diff-viewer']").text()).toContain("demo.txt");
  });
});
