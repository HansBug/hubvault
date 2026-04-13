import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CodeViewer from "@/components/CodeViewer.vue";

describe("CodeViewer", function suite() {
  it("renders code content with language metadata and line numbers", async function testCodeViewer() {
    const wrapper = mount(CodeViewer, {
      props: {
        path: "src/app.py",
        content: "print('hi')\nprint('bye')\n"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("python");
    expect(wrapper.text()).toContain("3 lines");
    expect(wrapper.html()).toContain("language-python");
    expect(wrapper.html()).toContain("line-numbers");
  });

  it("shows loading state and zero lines for empty content while honoring explicit languages", function testCodeViewerLoadingState() {
    const wrapper = mount(CodeViewer, {
      props: {
        path: "docs/config.txt",
        language: "json",
        content: "",
        loading: true
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("json");
    expect(wrapper.text()).toContain("0 lines");
    expect(wrapper.find(".el-skeleton").exists()).toBe(true);
    expect(wrapper.find("pre.code-viewer__pre").exists()).toBe(false);
  });
});
