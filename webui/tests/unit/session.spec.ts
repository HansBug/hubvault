import { beforeEach, describe, expect, it, vi } from "vitest";

const clientMocks = vi.hoisted(function buildClientMocks() {
  return {
    getRepoInfo: vi.fn(),
    getRepoRefs: vi.fn(),
    getServiceMeta: vi.fn(),
    getWhoAmI: vi.fn()
  };
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    getRepoInfo: clientMocks.getRepoInfo,
    getRepoRefs: clientMocks.getRepoRefs,
    getServiceMeta: clientMocks.getServiceMeta,
    getWhoAmI: clientMocks.getWhoAmI
  };
});

import {
  bootstrapSession,
  clearSession,
  hasSessionToken,
  restoreSessionToken,
  setSessionToken,
  useSessionStore
} from "@/stores/session";

describe("session store", function suite() {
  beforeEach(function resetState() {
    clearSession();
    window.sessionStorage.clear();
    vi.clearAllMocks();

    clientMocks.getServiceMeta
      .mockResolvedValueOnce({
        repo: {
          default_branch: "release/v1",
          head: "head-1"
        }
      })
      .mockResolvedValueOnce({
        repo: {
          default_branch: "release/v1",
          head: "head-2"
        }
      });
    clientMocks.getWhoAmI
      .mockResolvedValueOnce({
        access: "rw",
        can_write: true
      })
      .mockResolvedValueOnce({
        access: "rw",
        can_write: true
      });
    clientMocks.getRepoRefs
      .mockResolvedValueOnce({
        branches: [{ name: "release/v1" }, { name: "dev" }],
        tags: [{ name: "v1.0" }]
      })
      .mockResolvedValueOnce({
        branches: [{ name: "release/v1" }, { name: "dev" }, { name: "feature/ui" }],
        tags: [{ name: "v1.0" }]
      });
    clientMocks.getRepoInfo.mockResolvedValue({
      default_branch: "release/v1",
      head: "head-1"
    });
  });

  it("reuses cached base context until a force refresh is requested", async function testBootstrapForceRefresh() {
    setSessionToken("rw-token");

    await bootstrapSession("release/v1");
    await bootstrapSession("release/v1");

    expect(clientMocks.getServiceMeta).toHaveBeenCalledTimes(1);
    expect(clientMocks.getWhoAmI).toHaveBeenCalledTimes(1);
    expect(clientMocks.getRepoRefs).toHaveBeenCalledTimes(1);
    expect(clientMocks.getRepoInfo).toHaveBeenCalledTimes(2);
    expect(useSessionStore().state.refs?.branches).toHaveLength(2);

    await bootstrapSession("release/v1", { force: true });

    expect(clientMocks.getServiceMeta).toHaveBeenCalledTimes(2);
    expect(clientMocks.getWhoAmI).toHaveBeenCalledTimes(2);
    expect(clientMocks.getRepoRefs).toHaveBeenCalledTimes(2);
    expect(useSessionStore().state.refs?.branches).toHaveLength(3);
  });

  it("restores tokens, exposes hasToken, and clears stored session state", function testTokenPersistence() {
    window.sessionStorage.setItem("hubvault.webui.token", "persisted-token");

    restoreSessionToken();
    expect(hasSessionToken()).toBe(true);
    expect(useSessionStore().hasToken.value).toBe(true);

    clearSession();

    expect(hasSessionToken()).toBe(false);
    expect(useSessionStore().hasToken.value).toBe(false);
    expect(window.sessionStorage.getItem("hubvault.webui.token")).toBeNull();
  });

  it("rejects missing tokens and preserves readable bootstrap errors", async function testBootstrapErrors() {
    await expect(bootstrapSession("release/v1")).rejects.toThrow("Missing API token.");

    setSessionToken("rw-token");
    clientMocks.getServiceMeta.mockReset();
    clientMocks.getServiceMeta.mockRejectedValueOnce(new Error("meta unavailable"));

    await expect(bootstrapSession("release/v1")).rejects.toThrow("meta unavailable");
    expect(useSessionStore().state.error).toBe("meta unavailable");
  });

  it("falls back to repo-provided revisions and default bootstrap errors when metadata is sparse", async function testBootstrapFallbacks() {
    setSessionToken("rw-token");
    clientMocks.getServiceMeta.mockReset();
    clientMocks.getWhoAmI.mockReset();
    clientMocks.getRepoRefs.mockReset();
    clientMocks.getRepoInfo.mockReset();

    clientMocks.getServiceMeta.mockResolvedValueOnce({
      repo: {
        default_branch: ""
      }
    });
    clientMocks.getWhoAmI.mockResolvedValueOnce({
      access: "ro",
      can_write: false
    });
    clientMocks.getRepoRefs.mockResolvedValueOnce({
      branches: [],
      tags: []
    });
    clientMocks.getRepoInfo.mockResolvedValueOnce({
      default_branch: "fallback-main",
      head: "head-fallback"
    });

    await bootstrapSession("");

    expect(clientMocks.getRepoInfo).toHaveBeenCalledWith(undefined);
    expect(useSessionStore().state.repoRevision).toBe("fallback-main");

    clientMocks.getServiceMeta.mockRejectedValueOnce({});
    await expect(bootstrapSession("release/v1", { force: true })).rejects.toEqual({});
    expect(useSessionStore().state.error).toBe("Failed to load session data.");
  });

  it("trims stored tokens and tolerates missing sessionStorage during restoration", function testSessionStorageGuards() {
    const originalStorage = window.sessionStorage;

    setSessionToken("  rw-token  ");
    expect(window.sessionStorage.getItem("hubvault.webui.token")).toBe("rw-token");

    setSessionToken("");
    expect(window.sessionStorage.getItem("hubvault.webui.token")).toBeNull();

    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      value: null
    });

    expect(function restoreWithoutStorage() {
      restoreSessionToken();
    }).not.toThrow();

    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      value: originalStorage
    });
  });
});
