import { beforeEach, describe, expect, it, vi } from "vitest";

const routerState = vi.hoisted(function buildRouterState() {
  return {
    hasSessionToken: vi.fn(),
    setSessionToken: vi.fn()
  };
});

vi.mock("@/stores/session", function mockSessionStore() {
  return {
    hasSessionToken: routerState.hasSessionToken,
    setSessionToken: routerState.setSessionToken
  };
});

import router from "@/router";

describe("router", function suite() {
  beforeEach(async function resetRouter() {
    routerState.hasSessionToken.mockReset();
    routerState.setSessionToken.mockReset();
    if (!router.currentRoute.value.name) {
      await router.push("/login");
    }
  });

  it("redirects protected repo routes to login when no token is available", async function testAuthRedirect() {
    routerState.hasSessionToken.mockReturnValue(false);

    await router.push("/repo/files?revision=release%2Fv1");

    expect(router.currentRoute.value.name).toBe("login");
    expect(router.currentRoute.value.query.redirect).toBe("/repo/files?revision=release%2Fv1");
  });

  it("redirects authenticated users away from login and exposes the expected route tree", async function testLoginRedirectAndRoutes() {
    routerState.hasSessionToken.mockReturnValue(true);

    await router.push("/login");

    expect(router.currentRoute.value.name).toBe("overview");
    expect(
      router.getRoutes().map(function routeRecord(item) {
        return item.name;
      })
    ).toEqual(
      expect.arrayContaining(["login", "overview", "files", "upload", "file-detail", "commits", "commit-detail", "refs", "storage"])
    );
  });

  it("consumes token query parameters before entering protected routes", async function testTokenQueryBootstrap() {
    routerState.hasSessionToken.mockReturnValue(true);

    await router.push("/repo/blob/docs/guide.md?revision=release%2Fv1&token=secret-query-token");

    expect(routerState.setSessionToken).toHaveBeenCalledWith("secret-query-token");
    expect(router.currentRoute.value.name).toBe("file-detail");
    expect(router.currentRoute.value.query.token).toBeUndefined();
  });
});
