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

  it("keeps redirect URLs with an existing revision and falls back to the overview route otherwise", async function testRedirectBranches() {
    loginMocks.route.query = {
      redirect: "/repo/files?path=docs&revision=dev"
    };
    loginMocks.bootstrapSession.mockResolvedValueOnce({
      repoRevision: "release/v1"
    });

    const redirectWrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await redirectWrapper.get("input").setValue("rw-token");
    await redirectWrapper.get("form").trigger("submit");
    await flushPromises();

    expect(loginMocks.replace).toHaveBeenCalledWith("/repo/files?path=docs&revision=dev");

    loginMocks.route.query = {
      redirect: "/outside"
    };
    loginMocks.bootstrapSession.mockResolvedValueOnce({
      repoRevision: "release/v2"
    });

    const fallbackWrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await fallbackWrapper.get("input").setValue("ro-token");
    await fallbackWrapper.get("button").trigger("click");
    await flushPromises();

    expect(loginMocks.replace).toHaveBeenLastCalledWith({
      name: "overview",
      query: {
        revision: "release/v2"
      }
    });
  });

  it("adds revisions to bare repo redirects and uses the default auth failure copy", async function testBareRedirectAndFallbackError() {
    loginMocks.route.query = {
      redirect: "/repo/commits"
    };
    loginMocks.bootstrapSession.mockResolvedValueOnce({
      repoRevision: "release/v3"
    });

    const redirectWrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await redirectWrapper.get("input").setValue("rw-token");
    await redirectWrapper.get("button").trigger("click");
    await flushPromises();

    expect(loginMocks.replace).toHaveBeenCalledWith("/repo/commits?revision=release%2Fv3");

    loginMocks.route.query = {
      redirect: 123 as any
    };
    loginMocks.bootstrapSession.mockResolvedValueOnce({
      repoRevision: "release/v4"
    });

    const fallbackRedirectWrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await fallbackRedirectWrapper.get("input").setValue("rw-token");
    await fallbackRedirectWrapper.get("button").trigger("click");
    await flushPromises();

    expect(loginMocks.replace).toHaveBeenLastCalledWith({
      name: "overview",
      query: {
        revision: "release/v4"
      }
    });

    loginMocks.route.query = {
      redirect: 123 as any
    };
    loginMocks.bootstrapSession.mockRejectedValueOnce({});

    const errorWrapper = mount(LoginView, {
      global: {
        plugins: [ElementPlus]
      }
    });

    await errorWrapper.get("input").setValue("bad-token");
    await errorWrapper.get("button").trigger("click");
    await flushPromises();

    expect(errorWrapper.text()).toContain("Unable to authenticate with the provided token.");
  });
});
