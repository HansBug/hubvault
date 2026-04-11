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
    applyCommit: vi.fn(),
    deleteRepoFile: vi.fn(),
    deleteRepoFolder: vi.fn(),
    getPathsInfo: vi.fn(),
    getRepoTree: vi.fn(),
    planCommit: vi.fn(),
    bootstrapSession: vi.fn(),
    buildExactUploadManifest: vi.fn()
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
    applyCommit: filesViewMocks.applyCommit,
    deleteRepoFile: filesViewMocks.deleteRepoFile,
    deleteRepoFolder: filesViewMocks.deleteRepoFolder,
    getPathsInfo: filesViewMocks.getPathsInfo,
    getRepoTree: filesViewMocks.getRepoTree,
    planCommit: filesViewMocks.planCommit
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

vi.mock("@/utils/uploads", async function mockUploadsModule() {
  const actual = await vi.importActual<typeof import("@/utils/uploads")>("@/utils/uploads");
  return {
    ...actual,
    buildExactUploadManifest: filesViewMocks.buildExactUploadManifest
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

    await findButtonByText(wrapper, "delete docs/config.json").trigger("click");
    await flushPromises();

    expect(filesViewMocks.deleteRepoFile).toHaveBeenCalledWith({
      path_in_repo: "docs/config.json",
      revision: "release/v1",
      commit_message: "Delete docs/config.json with hubvault"
    });
    expect(filesViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });
  });

  it("queues uploads, submits them, and surfaces stale-plan errors with a refresh hint", async function testUploadQueue() {
    const file = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    filesViewMocks.route.query = {};
    filesViewMocks.getPathsInfo.mockResolvedValue([]);
    filesViewMocks.getRepoTree.mockResolvedValue([]);
    filesViewMocks.buildExactUploadManifest
      .mockResolvedValueOnce({
        operations: [
          {
            type: "add",
            path_in_repo: "notes.txt",
            size: 5,
            sha256: "abc",
            chunks: []
          }
        ],
        uploads: [
          {
            pathInRepo: "notes.txt",
            file: file
          }
        ]
      })
      .mockResolvedValueOnce({
        operations: [
          {
            type: "add",
            path_in_repo: "notes.txt",
            size: 5,
            sha256: "abc",
            chunks: []
          }
        ],
        uploads: [
          {
            pathInRepo: "notes.txt",
            file: file
          }
        ]
      });
    filesViewMocks.planCommit
      .mockResolvedValueOnce({
        base_head: "base-1",
        statistics: {
          planned_upload_bytes: 5,
          copy_file_count: 0,
          chunk_fast_upload_file_count: 0
        },
        operations: [
          {
            index: 0,
            type: "add",
            strategy: "upload-full",
            field_name: "upload_file_0"
          }
        ]
      })
      .mockRejectedValueOnce(new Error("branch head changed after upload planning; please re-plan the upload"));
    filesViewMocks.applyCommit.mockResolvedValue({
      oid: "upload-commit"
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

    const input = wrapper.get("[data-testid='upload-file-input']");
    const inputElement = input.element as HTMLInputElement;
    Object.defineProperty(inputElement, "files", {
      configurable: true,
      value: [file]
    });
    Object.defineProperty(inputElement, "value", {
      configurable: true,
      writable: true,
      value: "C:\\fakepath\\notes.txt"
    });

    await input.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("notes.txt");

    await wrapper.get("input[placeholder='Commit message for the queued upload batch']").setValue("upload notes");
    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(filesViewMocks.planCommit).toHaveBeenNthCalledWith(1, {
      revision: "release/v1",
      commit_message: "upload notes",
      operations: [
        {
          type: "add",
          path_in_repo: "notes.txt",
          size: 5,
          sha256: "abc",
          chunks: []
        }
      ]
    });
    expect(filesViewMocks.applyCommit).toHaveBeenCalledWith(
      {
        revision: "release/v1",
        parent_commit: "base-1",
        commit_message: "upload notes",
        operations: [
          {
            type: "add",
            path_in_repo: "notes.txt",
            size: 5,
            sha256: "abc",
            chunks: []
          }
        ],
        upload_plan: {
          base_head: "base-1",
          statistics: {
            planned_upload_bytes: 5,
            copy_file_count: 0,
            chunk_fast_upload_file_count: 0
          },
          operations: [
            {
              index: 0,
              type: "add",
              strategy: "upload-full",
              field_name: "upload_file_0"
            }
          ]
        }
      },
      [
        {
          fieldName: "upload_file_0",
          file: file,
          fileName: "notes.txt"
        }
      ],
      {
        onUploadProgress: expect.any(Function)
      }
    );

    Object.defineProperty(inputElement, "files", {
      configurable: true,
      value: [file]
    });
    await input.trigger("change");
    await flushPromises();
    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(wrapper.text()).toContain("Repository changed during upload planning. Refresh the page and retry the upload.");
  });
});
