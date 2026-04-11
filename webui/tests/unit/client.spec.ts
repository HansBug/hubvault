import { beforeEach, describe, expect, it, vi } from "vitest";

const axiosState = vi.hoisted(function buildAxiosState() {
  const state: Record<string, any> = {
    requestInterceptor: null,
    responseError: null
  };
  state.request = vi.fn(function request(config) {
    if (config.responseType === "arraybuffer") {
      return Promise.resolve({
        data: new Uint8Array([1, 2, 3]).buffer
      });
    }
    return Promise.resolve({
      data: {
        ok: true
      }
    });
  });
  state.client = {
    request: state.request,
    interceptors: {
      request: {
        use: vi.fn(function useRequestInterceptor(handler) {
          state.requestInterceptor = handler;
          return 0;
        })
      },
      response: {
        use: vi.fn(function useResponseInterceptor(_success, handler) {
          state.responseError = handler;
          return 0;
        })
      }
    }
  };
  state.create = vi.fn(function createClient() {
    return state.client;
  });
  return state;
});

vi.mock("axios", function mockAxiosModule() {
  return {
    default: {
      create: axiosState.create
    }
  };
});

import * as apiClient from "@/api/client";

describe("api client helpers", function suite() {
  beforeEach(function resetClientState() {
    window.sessionStorage.clear();
    vi.clearAllMocks();
  });

  it("attaches bearer tokens and maps error payloads", async function testInterceptors() {
    window.sessionStorage.setItem("hubvault.webui.token", "secret-token");

    const config = axiosState.requestInterceptor({
      headers: {}
    });

    expect(config.headers.Authorization).toBe("Bearer secret-token");

    try {
      axiosState.responseError({
        response: {
          status: 409,
          data: {
            error: {
              message: "write conflict"
            }
          }
        }
      });
    } catch (error) {
      expect(error).toMatchObject({
        message: "write conflict",
        status: 409,
        payload: {
          error: {
            message: "write conflict"
          }
        }
      });
    }

    try {
      axiosState.responseError({
        response: {
          status: 422,
          data: {
            detail: "invalid request"
          }
        }
      });
    } catch (error) {
      expect(error).toMatchObject({
        message: "invalid request",
        status: 422,
        payload: {
          detail: "invalid request"
        }
      });
    }

    try {
      axiosState.responseError({
        response: {
          status: 500,
          data: {}
        }
      });
    } catch (error) {
      expect(error).toMatchObject({
        message: "Request failed with status 500.",
        status: 500,
        payload: {}
      });
    }

    await expect(
      Promise.resolve().then(function callNetworkError() {
        return axiosState.responseError({
          request: {}
        });
      })
    ).rejects.toMatchObject({
      message: "Unable to reach the hubvault server.",
      status: 0
    });

    const setupError = new Error("bad setup");
    expect(function callSetupError() {
      axiosState.responseError(setupError);
    }).toThrow(setupError);
  });

  it("leaves anonymous requests unchanged", function testAnonymousRequest() {
    const config = axiosState.requestInterceptor({});

    expect(config).toEqual({});
  });

  it("builds request payloads for the full public client surface", async function testRequestBuilders() {
    const file = new File(["hello"], "demo.txt", {
      type: "text/plain"
    });

    await apiClient.getServiceMeta();
    await apiClient.getWhoAmI();
    await apiClient.getRepoInfo("release/v1");
    await apiClient.getRepoRefs();
    await apiClient.getRepoFiles("release/v1");
    await apiClient.getRepoTree("release/v1", "docs");
    await apiClient.getRepoTree("release/v1", "");
    await apiClient.getPathsInfo("release/v1", ["docs/config.json"]);
    await apiClient.getBlobBytes("release/v1", "docs/config.json");
    await apiClient.getCommits("release/v1", true);
    await apiClient.getCommitDetail("commit-1", true);
    await apiClient.getStorageOverview();
    await apiClient.runQuickVerify();
    await apiClient.runFullVerify();
    await apiClient.planCommit({
      revision: "release/v1"
    });
    await apiClient.applyCommit(
      {
        revision: "release/v1"
      },
      []
    );
    await apiClient.applyCommit(
      {
        revision: "release/v1"
      },
      [
        {
          fieldName: "upload_file_0",
          file: file,
          fileName: "demo.txt"
        }
      ],
      {
        onUploadProgress: vi.fn()
      }
    );
    await apiClient.applyCommit(
      {
        revision: "release/v1"
      },
      undefined
    );
    await apiClient.createBranchRef({
      branch: "dev"
    });
    await apiClient.deleteBranchRef("release/v1");
    await apiClient.createTagRef({
      tag: "v1.0"
    });
    await apiClient.deleteTagRef("v1.0");
    await apiClient.mergeRevision({
      source_revision: "feature",
      target_revision: "release/v1"
    });
    await apiClient.resetBranchRef({
      ref_name: "release/v1",
      to_revision: "dev"
    });
    await apiClient.deleteRepoFile({
      path_in_repo: "docs/config.json"
    });
    await apiClient.deleteRepoFolder({
      path_in_repo: "docs"
    });
    await apiClient.runGc({
      dry_run: true
    });
    await apiClient.runGc();
    await apiClient.runSquashHistory({
      ref_name: "release/v1"
    });

    expect(apiClient.buildBlobUrl("release/v1", "docs/read me#.md")).toBe(
      "/api/v1/content/blob/docs/read%20me%23.md?revision=release%2Fv1"
    );
    expect(apiClient.buildDownloadUrl("release/v1", "docs/read me#.md")).toBe(
      "/api/v1/content/download/docs/read%20me%23.md?revision=release%2Fv1"
    );
    expect(apiClient.buildDownloadUrl("release/v1", "docs/config.json")).toBe(
      "/api/v1/content/download/docs/config.json?revision=release%2Fv1"
    );

    window.sessionStorage.setItem("hubvault.webui.token", "secret-token");
    expect(apiClient.buildBlobUrl("release/v1", "docs/read me#.md")).toBe(
      "/api/v1/content/blob/docs/read%20me%23.md?revision=release%2Fv1&token=secret-token"
    );
    expect(apiClient.buildDownloadUrl("release/v1", "docs/config.json")).toBe(
      "/api/v1/content/download/docs/config.json?revision=release%2Fv1&token=secret-token"
    );

    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/meta/service"
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/meta/whoami"
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/repo",
      params: {
        revision: "release/v1"
      }
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/content/tree",
      params: {
        revision: "release/v1",
        path_in_repo: "docs"
      }
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/content/tree",
      params: {
        revision: "release/v1"
      }
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/content/paths-info",
      params: {
        revision: "release/v1"
      },
      data: ["docs/config.json"]
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/content/blob/docs/config.json",
      params: {
        revision: "release/v1"
      },
      responseType: "arraybuffer"
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "get",
      url: "/api/v1/history/commits/commit-1",
      params: {
        formatted: true
      }
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/write/commit",
      data: {
        revision: "release/v1"
      }
    });
    expect(axiosState.request.mock.calls.some(function hasMultipartCall(call) {
      const config = call[0];
      return config.url === "/api/v1/write/commit"
        && config.data instanceof FormData
        && typeof config.onUploadProgress === "function";
    })).toBe(true);
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "delete",
      url: "/api/v1/write/branches/release%2Fv1"
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "delete",
      url: "/api/v1/write/tags/v1.0"
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/maintenance/gc",
      data: {
        dry_run: true
      }
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/maintenance/gc",
      data: {}
    });
    expect(axiosState.request).toHaveBeenCalledWith({
      method: "post",
      url: "/api/v1/maintenance/squash-history",
      data: {
        ref_name: "release/v1"
      }
    });
  });
});
