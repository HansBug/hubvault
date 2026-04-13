import ElementPlus, { ElMessage, ElMessageBox } from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const filesViewMocks = vi.hoisted(function buildFilesViewMocks() {
  return {
    route: {
      query: {} as Record<string, unknown>
    },
    push: vi.fn(),
    deleteRepoFile: vi.fn(),
    deleteRepoFolder: vi.fn(),
    getPathsInfo: vi.fn(),
    getRepoTree: vi.fn(),
    bootstrapSession: vi.fn()
  };
});

const sessionState = reactive({
  auth: null as any
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRoute: function useRoute() {
      return filesViewMocks.route;
    },
    useRouter: function useRouter() {
      return {
        push: filesViewMocks.push
      };
    }
  };
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    deleteRepoFile: filesViewMocks.deleteRepoFile,
    deleteRepoFolder: filesViewMocks.deleteRepoFolder,
    getPathsInfo: filesViewMocks.getPathsInfo,
    getRepoTree: filesViewMocks.getRepoTree
  };
});

vi.mock("@/stores/session", function mockSessionStore() {
  return {
    bootstrapSession: filesViewMocks.bootstrapSession,
    useSessionStore: function useSessionStore() {
      return {
        state: readonly(sessionState)
      };
    }
  };
});

vi.mock("@/components/FileTable.vue", function mockFileTable() {
  return {
    default: {
      props: ["entries", "revision", "canWrite"],
      template: [
        "<div data-testid=\"file-table\">",
        "  <button",
        "    v-for=\"entry in entries\"",
        "    :key=\"entry.path + '-open'\"",
        "    @click=\"$emit(entry.entry_type === 'folder' ? 'open-folder' : 'open-file', entry.path)\"",
        "  >",
        "    open {{ entry.path }}",
        "  </button>",
        "  <button",
        "    v-for=\"entry in entries\"",
        "    :key=\"entry.path + '-commit'\"",
        "    @click=\"$emit('open-commit', entry.last_commit && entry.last_commit.oid)\"",
        "  >",
        "    commit {{ entry.path }}",
        "  </button>",
        "  <button",
        "    v-for=\"entry in entries\"",
        "    :key=\"entry.path + '-delete'\"",
        "    @click=\"$emit('delete-entry', entry)\"",
        "  >",
        "    delete {{ entry.path }}",
        "  </button>",
        "</div>"
      ].join("")
    }
  };
});

import FilesView from "@/views/FilesView.vue";

function findButtonByText(wrapper, text: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(text) >= 0;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("FilesView", function suite() {
  beforeEach(function resetFilesViewMocks() {
    vi.clearAllMocks();
    sessionState.auth = {
      access: "rw",
      can_write: true
    };
    filesViewMocks.route.query = {
      path: "docs"
    };
    filesViewMocks.getPathsInfo.mockResolvedValue([
      {
        path: "docs",
        entry_type: "folder"
      }
    ]);
    filesViewMocks.getRepoTree.mockResolvedValue([
      {
        path: "docs/config.json",
        entry_type: "file",
        size: 14,
        last_commit: {
          oid: "commit-config",
          title: "add config",
          date: "2026-04-12T00:00:00Z"
        }
      }
    ]);
    vi.spyOn(ElMessage, "success").mockImplementation(function swallowSuccess() {
      return undefined as never;
    });
  });

  it("loads a directory and deletes a file through the write API", async function testDeleteFlow() {
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);
    filesViewMocks.deleteRepoFile.mockResolvedValue({
      oid: "delete-commit"
    });

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(filesViewMocks.getPathsInfo).toHaveBeenCalledWith("release/v1", ["docs"]);
    expect(filesViewMocks.getRepoTree).toHaveBeenCalledWith("release/v1", "docs");
    expect(wrapper.text()).not.toContain("<home>");
    expect(wrapper.find("[aria-label='Repository root']").exists()).toBe(true);

    await findButtonByText(wrapper, "delete docs/config.json").trigger("click");
    await flushPromises();

    expect(filesViewMocks.deleteRepoFile).toHaveBeenCalledWith({
      path_in_repo: "docs/config.json",
      revision: "release/v1",
      commit_message: "Delete docs/config.json with hubvault"
    });
    expect(filesViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });
  });

  it("routes to the dedicated upload page and commit detail page", async function testNavigationActions() {
    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await wrapper.get("[data-testid='files-upload-button']").trigger("click");
    expect(filesViewMocks.push).toHaveBeenLastCalledWith({
      name: "upload",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });

    await findButtonByText(wrapper, "commit docs/config.json").trigger("click");
    expect(filesViewMocks.push).toHaveBeenLastCalledWith({
      name: "commit-detail",
      params: {
        commitId: "commit-config"
      },
      query: {
        revision: "release/v1"
      }
    });
  });

  it("redirects file paths into file detail views", async function testFileRedirects() {
    filesViewMocks.route.query = {
      path: "docs/config.json"
    };
    filesViewMocks.getPathsInfo.mockResolvedValue([
      {
        path: "docs/config.json",
        entry_type: "file"
      }
    ]);

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(filesViewMocks.push).toHaveBeenCalledWith({
      name: "file-detail",
      params: {
        pathMatch: ["docs", "config.json"]
      },
      query: {
        revision: "release/v1"
      }
    });
    expect(filesViewMocks.getRepoTree).not.toHaveBeenCalled();
  });

  it("supports folder deletion from directory listings", async function testFolderDelete() {
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);
    filesViewMocks.route.query = {
      path: "docs"
    };
    filesViewMocks.getRepoTree.mockResolvedValue([
      {
        path: "docs/subdir",
        entry_type: "folder",
        size: 0,
        last_commit: {
          oid: "commit-folder",
          title: "add folder",
          date: "2026-04-12T00:00:00Z"
        }
      }
    ]);
    filesViewMocks.deleteRepoFolder.mockResolvedValue({
      oid: "delete-folder-commit"
    });

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await findButtonByText(wrapper, "delete docs/subdir").trigger("click");
    await flushPromises();

    expect(filesViewMocks.deleteRepoFolder).toHaveBeenCalledWith({
      path_in_repo: "docs/subdir",
      revision: "release/v1",
      commit_message: "Delete folder docs/subdir with hubvault"
    });
  });

  it("keeps the current file list stable when deletion is cancelled or fails", async function testDeleteGuards() {
    const confirmSpy = vi.spyOn(ElMessageBox, "confirm");
    confirmSpy.mockRejectedValueOnce("cancel" as never);
    confirmSpy.mockResolvedValueOnce(undefined as never);
    filesViewMocks.deleteRepoFile.mockRejectedValueOnce(new Error("delete failed"));

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await findButtonByText(wrapper, "delete docs/config.json").trigger("click");
    await flushPromises();
    expect(filesViewMocks.deleteRepoFile).not.toHaveBeenCalled();

    await findButtonByText(wrapper, "delete docs/config.json").trigger("click");
    await flushPromises();

    expect(filesViewMocks.deleteRepoFile).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("delete failed");
  });

  it("loads repository root listings, routes folder clicks, and hides upload actions for read-only sessions", async function testRootListingFlow() {
    sessionState.auth = {
      access: "r",
      can_write: false
    };
    filesViewMocks.route.query = {};
    filesViewMocks.getRepoTree.mockResolvedValue([
      {
        path: "docs",
        entry_type: "folder",
        size: 0,
        last_commit: {
          oid: "commit-docs",
          title: "add docs",
          date: "2026-04-12T00:00:00Z"
        }
      }
    ]);

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(filesViewMocks.getPathsInfo).not.toHaveBeenCalled();
    expect(filesViewMocks.getRepoTree).toHaveBeenCalledWith("release/v1", "");
    expect(wrapper.find("[data-testid='files-upload-button']").exists()).toBe(false);

    await findButtonByText(wrapper, "open docs").trigger("click");
    expect(filesViewMocks.push).toHaveBeenLastCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });
  });

  it("shows a stable fallback error when file listing fails without a message", async function testListErrorFallback() {
    filesViewMocks.route.query = {};
    filesViewMocks.getRepoTree.mockRejectedValueOnce({});

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(wrapper.text()).toContain("Unable to load repository files.");
  });

  it("uses unresolved route paths directly and keeps root upload navigation query-free", async function testRouteFallbackBranches() {
    filesViewMocks.route.query = {
      path: "missing/folder"
    };
    filesViewMocks.getPathsInfo.mockResolvedValueOnce([]);
    filesViewMocks.getRepoTree.mockResolvedValueOnce([]);

    const missingWrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    expect(filesViewMocks.getRepoTree).toHaveBeenCalledWith("release/v1", "missing/folder");

    filesViewMocks.route.query = {};
    filesViewMocks.getRepoTree.mockResolvedValueOnce([]);

    const rootWrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await rootWrapper.get("[data-testid='files-upload-button']").trigger("click");
    expect(filesViewMocks.push).toHaveBeenLastCalledWith({
      name: "upload",
      query: {
        revision: "release/v1",
        path: undefined
      }
    });
  });

  it("treats closed delete dialogs as no-ops and uses the default delete error copy", async function testDeleteFallbackCopy() {
    const confirmSpy = vi.spyOn(ElMessageBox, "confirm");
    confirmSpy.mockRejectedValueOnce("close" as never);
    confirmSpy.mockResolvedValueOnce(undefined as never);
    filesViewMocks.deleteRepoFile.mockRejectedValueOnce({});

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await findButtonByText(wrapper, "delete docs/config.json").trigger("click");
    await flushPromises();
    expect(filesViewMocks.deleteRepoFile).not.toHaveBeenCalled();

    await findButtonByText(wrapper, "delete docs/config.json").trigger("click");
    await flushPromises();

    expect(wrapper.text()).toContain("Unable to delete the selected entry.");
  });

  it("rethrows unexpected delete dialog failures instead of silently swallowing them", async function testDeleteDialogErrors() {
    const dialogError = new Error("dialog transport failed");
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValueOnce(dialogError as never);

    const wrapper = mount(FilesView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await flushPromises();

    await expect(
      (wrapper.vm as any).handleDeleteEntry({
        path: "docs/config.json",
        entry_type: "file"
      })
    ).rejects.toThrow("dialog transport failed");
  });
});
