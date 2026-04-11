import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ReadmeViewer from "@/components/ReadmeViewer.vue";

describe("ReadmeViewer", function suite() {
  it("renders sanitized markdown", function testMarkdownRender() {
    const wrapper = mount(ReadmeViewer, {
      props: {
        path: "README.md",
        content: "# Demo\n\n<script>alert(1)</script>\n\nVisible text"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.html()).toContain("Visible text");
    expect(wrapper.html()).not.toContain("<script>");
  });
});
