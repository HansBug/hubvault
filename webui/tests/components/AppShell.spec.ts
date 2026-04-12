import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const appShellMocks = vi.hoisted(function buildAppShellMocks() {
  return {
    route: {
      name: "overview"
    },
    push: vi.fn()
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRoute: function useRoute() {
      return appShellMocks.route;
    },
    useRouter: function useRouter() {
      return {
        push: appShellMocks.push
      };
    }
  };
});

import AppShell from "@/components/AppShell.vue";

function findButtonByText(wrapper, text: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(text) >= 0;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("AppShell", function suite() {
  it("renders shell metadata, routes menu selections, and emits revision/logout actions", async function testAppShell() {
    const wrapper = mount(AppShell, {
      props: {
        service: {
          mode: "frontend",
          repo: {
            default_branch: "release/v1",
            head: "1234567890abcdef1234567890abcdef12345678",
            path: "/tmp/repo"
          }
        },
        auth: {
          access: "rw"
        },
        refs: {
          branches: [{ name: "release/v1" }, { name: "dev" }],
          tags: [{ name: "v1.0" }]
        },
        repo: {
          default_branch: "release/v1",
          head: "1234567890abcdef1234567890abcdef12345678"
        },
        currentRevision: "release/v1"
      },
      slots: {
        default: "<div data-testid=\"shell-slot\">child</div>"
      },
      global: {
        plugins: [ElementPlus],
        stubs: {
          RepoRevisionSwitch: {
            template: "<button data-testid=\"revision-switch\" @click=\"$emit('update:modelValue', 'dev')\">switch</button>"
          }
        }
      }
    });

    await wrapper.get("[data-testid='revision-switch']").trigger("click");
    await findButtonByText(wrapper, "Logout").trigger("click");
    await wrapper.findAll(".el-menu-item")[1].trigger("click");

    expect(wrapper.emitted("change-revision")).toEqual([["dev"]]);
    expect(wrapper.emitted("logout")).toHaveLength(1);
    expect(appShellMocks.push).toHaveBeenCalledWith({
      name: "files",
      query: {
        revision: "release/v1"
      }
    });
    expect(wrapper.text()).toContain("Read / Write");
    expect(wrapper.text()).toContain("/tmp/repo");
    expect(wrapper.text()).toContain("child");
  });
});
