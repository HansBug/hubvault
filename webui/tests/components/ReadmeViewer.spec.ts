import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import ReadmeViewer from "@/components/ReadmeViewer.vue";

describe("ReadmeViewer", function suite() {
  it("renders sanitized markdown with highlighted fenced code blocks", function testMarkdownRender() {
    const wrapper = mount(ReadmeViewer, {
      props: {
        path: "README.md",
        content: `# Demo

| Column | Very Long Column |
| --- | --- |
| alpha | a-very-very-very-very-very-very-long-token-that-should-still-stay-inside-the-readme-card |

![Fixture image](/api/v1/content/blob/images/logo.svg?revision=release%2Fv1&token=ro-token)

\`\`\`python
def demo():
    return 1
\`\`\`

<script>alert(1)</script>

Visible text`
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.get("[data-testid='readme-viewer-markdown']").text()).toContain("Visible text");
    expect(wrapper.html()).not.toContain("<script>");
    expect(wrapper.html()).toContain("language-python");
    expect(wrapper.html()).toContain("token keyword");
    expect(wrapper.find("table").exists()).toBe(true);
    expect(wrapper.find("img").attributes("src")).toContain("/api/v1/content/blob/images/logo.svg");
  });

  it("renders loading, empty, and plain-text fallback states through public props", function testNonMarkdownStates() {
    const loadingWrapper = mount(ReadmeViewer, {
      props: {
        path: "README.md",
        content: "",
        loading: true
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(loadingWrapper.html()).toContain("el-skeleton");

    const emptyWrapper = mount(ReadmeViewer, {
      props: {
        path: "README.md",
        content: "",
        emptyTitle: "No README",
        emptyDescription: "Custom empty message"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(emptyWrapper.text()).toContain("No README");
    expect(emptyWrapper.text()).toContain("Custom empty message");

    const plainWrapper = mount(ReadmeViewer, {
      props: {
        path: "notes.txt",
        content: "plain preview body"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(plainWrapper.text()).toContain("plain preview body");
    expect(plainWrapper.find("[data-testid='readme-viewer-markdown']").exists()).toBe(false);
  });
});
