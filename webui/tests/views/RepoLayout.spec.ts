import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const repoLayoutMocks = vi.hoisted(function buildRepoLayoutMocks() {
  return {
    route: {
      name: "overview",
      query: {} as Record<string, unknown>,
      fullPath: "/repo/overview"
    },
    replace: vi.fn(),
    push: vi.fn(),
    bootstrapSession: vi.fn(),
    clearSession: vi.fn()
  };
});

const sessionState = reactive({
  service: null as any,
  auth: null as any,
  refs: null as any,
  repo: null as any,
  repoRevision: ""
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRoute: function useRoute() {
      return repoLayoutMocks.route;
    },
    useRouter: function useRouter() {
      return {
        replace: repoLayoutMocks.replace,
        push: repoLayoutMocks.push
      };
    }
  };
});

vi.mock("@/stores/session", function mockSessionStore() {
  return {
    bootstrapSession: repoLayoutMocks.bootstrapSession,
    clearSession: repoLayoutMocks.clearSession,
    useSessionStore: function useSessionStore() {
      return {
        state: readonly(sessionState)
      };
    }
  };
});

vi.mock("@/components/AppShell.vue", function mockAppShell() {
  return {
    default: {
      props: ["currentRevision"],
      template: [
        "<div data-testid=\"app-shell-stub\">",
        "  <button data-testid=\"emit-change\" @click=\"$emit('change-revision', 'dev')\">change</button>",
        "  <button data-testid=\"emit-logout\" @click=\"$emit('logout')\">logout</button>",
        "  <div data-testid=\"shell-revision\">{{ currentRevision }}</div>",
        "  <slot />",
        "</div>"
      ].join("")
    }
  };
});

const RouterViewStub = {
  setup(_props, context) {
    return function renderRouterView() {
      if (!context.slots.default) {
        return null;
      }
      return context.slots.default({
        Component: {
          props: ["revision"],
          template: "<div data-testid=\"route-child\">{{ revision }}</div>"
        }
      });
    };
  }
};

import RepoLayout from "@/views/RepoLayout.vue";

describe("RepoLayout", function suite() {
  beforeEach(function resetRepoLayoutState() {
    vi.clearAllMocks();
    repoLayoutMocks.route.name = "overview";
    repoLayoutMocks.route.query = {};
    repoLayoutMocks.route.fullPath = "/repo/overview";
    sessionState.service = null;
    sessionState.auth = null;
    sessionState.refs = null;
    sessionState.repo = null;
    sessionState.repoRevision = "";
  });

  it("bootstraps session state, updates the route revision, and forwards shell events", async function testRepoLayoutSuccess() {
    repoLayoutMocks.bootstrapSession.mockImplementationOnce(async function bootstrap() {
      sessionState.service = {
        repo: {
          default_branch: "release/v1"
        }
      };
      sessionState.repo = {
        default_branch: "release/v1"
      };
      sessionState.repoRevision = "release/v1";
    });

    const wrapper = mount(RepoLayout, {
      global: {
        stubs: {
          RouterView: RouterViewStub,
          ElAlert: {
            props: ["title"],
            template: "<div class=\"el-alert\">{{ title }}</div>"
          },
          ElSkeleton: {
            template: "<div class=\"el-skeleton\"></div>"
          }
        }
      }
    });

    await flushPromises();

    expect(repoLayoutMocks.bootstrapSession).toHaveBeenCalledWith("");
    expect(repoLayoutMocks.replace).toHaveBeenCalledWith({
      name: "overview",
      query: {
        revision: "release/v1"
      }
    });
    expect(wrapper.get("[data-testid='route-child']").text()).toBe("release/v1");

    await wrapper.get("[data-testid='emit-change']").trigger("click");
    await wrapper.get("[data-testid='emit-logout']").trigger("click");

    expect(repoLayoutMocks.push).toHaveBeenCalledWith({
      name: "overview",
      query: {
        revision: "dev"
      }
    });
    expect(repoLayoutMocks.clearSession).toHaveBeenCalledTimes(1);
  });

  it("redirects to login when bootstrap returns an auth failure", async function testRepoLayoutAuthFailure() {
    repoLayoutMocks.route.fullPath = "/repo/files?path=docs";
    repoLayoutMocks.bootstrapSession.mockRejectedValueOnce({
      status: 401,
      message: "bad token"
    });

    mount(RepoLayout, {
      global: {
        stubs: {
          RouterView: RouterViewStub,
          ElAlert: {
            props: ["title"],
            template: "<div class=\"el-alert\">{{ title }}</div>"
          },
          ElSkeleton: {
            template: "<div class=\"el-skeleton\"></div>"
          }
        }
      }
    });
    await flushPromises();

    expect(repoLayoutMocks.clearSession).toHaveBeenCalledTimes(1);
    expect(repoLayoutMocks.replace).toHaveBeenCalledWith({
      name: "login",
      query: {
        redirect: "/repo/files?path=docs"
      }
    });
  });
});
