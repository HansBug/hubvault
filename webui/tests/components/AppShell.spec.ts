import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  beforeEach(function resetAppShellMocks() {
    appShellMocks.route.name = "overview";
    appShellMocks.push.mockReset();
  });

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

  it("maps detail routes onto top-level navigation items and resolves head fallbacks", function testShellRouteMapping() {
    appShellMocks.route.name = "file-detail";
    const fileDetailWrapper = mount(AppShell, {
      props: {
        service: {
          mode: "frontend",
          repo: {
            default_branch: "main",
            head: "fedcba0987654321fedcba0987654321fedcba09"
          }
        },
        auth: {
          access: "ro"
        },
        currentRevision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(fileDetailWrapper.find(".el-menu-item.is-active").text()).toContain("Files");
    expect(fileDetailWrapper.text()).toContain("Read Only");
    expect(fileDetailWrapper.text()).toContain("fedcba0987");

    appShellMocks.route.name = "commit-detail";
    const commitDetailWrapper = mount(AppShell, {
      props: {
        currentRevision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(commitDetailWrapper.find(".el-menu-item.is-active").text()).toContain("Commits");
    expect(commitDetailWrapper.text()).toContain("head: empty");
  });

  it("maps upload routes back to files and defaults unknown routes to overview", function testShellDefaultRouteMapping() {
    appShellMocks.route.name = "upload";
    const uploadWrapper = mount(AppShell, {
      props: {
        currentRevision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(uploadWrapper.find(".el-menu-item.is-active").text()).toContain("Files");

    appShellMocks.route.name = null as any;
    const overviewWrapper = mount(AppShell, {
      props: {
        currentRevision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });
    expect(overviewWrapper.find(".el-menu-item.is-active").text()).toContain("Overview");
  });
});
