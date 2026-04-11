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

import { bootstrapSession, clearSession, setSessionToken, useSessionStore } from "@/stores/session";

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
});
