import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const loginMocks = vi.hoisted(function buildLoginMocks() {
  return {
    route: {
      query: {} as Record<string, unknown>
    },
    replace: vi.fn(),
    bootstrapSession: vi.fn(),
    clearSession: vi.fn(),
    setSessionToken: vi.fn()
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRoute: function useRoute() {
      return loginMocks.route;
    },
    useRouter: function useRouter() {
      return {
        replace: loginMocks.replace
      };
    }
  };
});

vi.mock("@/stores/session", function mockSessionStore() {
  return {
    bootstrapSession: loginMocks.bootstrapSession,
    clearSession: loginMocks.clearSession,
    setSessionToken: loginMocks.setSessionToken
  };
});

import LoginView from "@/views/LoginView.vue";

describe("LoginView", function suite() {
  it("logs in and redirects back into the repo route", async function testLoginRedirect() {
    loginMocks.route.query = {
      redirect: "/repo/files?path=docs"
    };
    loginMocks.bootstrapSession.mockResolvedValueOnce({
      repoRevision: "release/v1"
    });

    const wrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await wrapper.get("input").setValue("rw-token");
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(loginMocks.setSessionToken).toHaveBeenCalledWith("rw-token");
    expect(loginMocks.bootstrapSession).toHaveBeenCalledWith("");
    expect(loginMocks.replace).toHaveBeenCalledWith("/repo/files?path=docs&revision=release%2Fv1");
  });

  it("clears the session and shows an error when authentication fails", async function testLoginFailure() {
    loginMocks.route.query = {};
    loginMocks.bootstrapSession.mockRejectedValueOnce(new Error("bad token"));

    const wrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await wrapper.get("input").setValue("bad-token");
    await wrapper.get("button").trigger("click");
    await flushPromises();

    expect(loginMocks.clearSession).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("bad token");
  });
});
