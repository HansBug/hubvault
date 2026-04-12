import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const breadcrumbMocks = vi.hoisted(function buildBreadcrumbMocks() {
  return {
    push: vi.fn()
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRouter: function useRouter() {
      return {
        push: breadcrumbMocks.push
      };
    }
  };
});

import PathBreadcrumb from "@/components/PathBreadcrumb.vue";

function findButtonByLabelOrText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(value) >= 0 || item.attributes("aria-label") === value;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("PathBreadcrumb", function suite() {
  it("renders a hf-style text breadcrumb and routes across levels", async function testPathBreadcrumb() {
    const wrapper = mount(PathBreadcrumb, {
      props: {
        items: [
          {
            home: true,
            label: "<home>",
            ariaLabel: "Repository root",
            to: {
              name: "files",
              query: {
                revision: "release/v1"
              }
            }
          },
          {
            label: "src",
            to: {
              name: "files",
              query: {
                revision: "release/v1",
                path: "src"
              }
            }
          },
          {
            label: "app.py",
            current: true,
            to: {
              name: "file-detail",
              params: {
                pathMatch: ["src", "app.py"]
              },
              query: {
                revision: "release/v1"
              }
            }
          }
        ]
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("<home>");
    expect(wrapper.text()).toContain("src");
    expect(wrapper.text()).toContain("app.py");
    expect(wrapper.text()).toContain("/");

    await findButtonByLabelOrText(wrapper, "Repository root").trigger("click");
    await findButtonByLabelOrText(wrapper, "src").trigger("click");

    expect(breadcrumbMocks.push).toHaveBeenNthCalledWith(1, {
      name: "files",
      query: {
        revision: "release/v1"
      }
    });
    expect(breadcrumbMocks.push).toHaveBeenNthCalledWith(2, {
      name: "files",
      query: {
        revision: "release/v1",
        path: "src"
      }
    });
  });
});
