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
    expect(wrapper.text()).toContain("<home>");

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
});
