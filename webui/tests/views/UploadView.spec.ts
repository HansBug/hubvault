import ElementPlus, { ElMessage } from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const uploadViewMocks = vi.hoisted(function buildUploadViewMocks() {
  return {
    route: {
      query: {} as Record<string, unknown>
    },
    push: vi.fn(),
    applyCommit: vi.fn(),
    getPathsInfo: vi.fn(),
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
      return uploadViewMocks.route;
    },
    useRouter: function useRouter() {
      return {
        push: uploadViewMocks.push
      };
    }
  };
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    applyCommit: uploadViewMocks.applyCommit,
    getPathsInfo: uploadViewMocks.getPathsInfo,
    planCommit: uploadViewMocks.planCommit
  };
});

vi.mock("@/stores/session", function mockSessionStore() {
  return {
    bootstrapSession: uploadViewMocks.bootstrapSession,
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
    buildExactUploadManifest: uploadViewMocks.buildExactUploadManifest
  };
});

import UploadView from "@/views/UploadView.vue";

function setInputFiles(input: HTMLInputElement, files: File[]) {
  Object.defineProperty(input, "files", {
    configurable: true,
    value: files
  });
  Object.defineProperty(input, "value", {
    configurable: true,
    writable: true,
    value: "C:\\fakepath\\" + files.map(function joinNames(file) {
      return file.name;
    }).join(",")
  });
}

function findButtonByText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(value) >= 0;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("UploadView", function suite() {
  beforeEach(function resetUploadViewMocks() {
    vi.clearAllMocks();
    sessionState.auth = {
      access: "rw",
      can_write: true
    };
    uploadViewMocks.route.query = {
      path: "docs"
    };
    uploadViewMocks.getPathsInfo.mockResolvedValue([
      {
        path: "docs",
        entry_type: "folder"
      }
    ]);
    uploadViewMocks.buildExactUploadManifest.mockImplementation(async function buildManifest(entries) {
      return {
        operations: entries.map(function mapEntry(item) {
          return {
            type: "add",
            path_in_repo: item.pathInRepo,
            size: item.file.size,
            sha256: item.pathInRepo + "-sha256",
            chunks: []
          };
        }),
        uploads: entries.map(function mapUpload(item) {
          return {
            pathInRepo: item.pathInRepo,
            file: item.file
          };
        })
      };
    });
    vi.spyOn(ElMessage, "success").mockImplementation(function swallowSuccess() {
      return undefined as never;
    });
  });

  it("queues files across multiple additions and commits them from the dedicated upload page", async function testUploadQueue() {
    const firstFile = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    const secondFile = new File(["second"], "second.txt", {
      type: "text/plain"
    });
    uploadViewMocks.planCommit.mockResolvedValue({
      base_head: "base-1",
      statistics: {
        planned_upload_bytes: 11,
        copy_file_count: 0,
        chunk_fast_upload_file_count: 0
      },
      operations: [
        {
          index: 0,
          type: "add",
          strategy: "upload-full",
          field_name: "upload_file_0"
        },
        {
          index: 1,
          type: "add",
          strategy: "upload-full",
          field_name: "upload_file_1"
        }
      ]
    });
    uploadViewMocks.applyCommit.mockResolvedValue({
      oid: "upload-commit"
    });

    const wrapper = mount(UploadView, {
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
    setInputFiles(inputElement, [firstFile]);
    await input.trigger("change");
    await flushPromises();

    setInputFiles(inputElement, [secondFile]);
    await input.trigger("change");
    await flushPromises();

    expect(wrapper.text()).toContain("docs/notes.txt");
    expect(wrapper.text()).toContain("docs/second.txt");
    expect(wrapper.text()).toContain("2 files queued");

    await wrapper.get("input[placeholder='Commit message for the queued upload batch']").setValue("upload notes");
    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(uploadViewMocks.planCommit).toHaveBeenCalledWith({
      revision: "release/v1",
      commit_message: "upload notes",
      operations: [
        {
          type: "add",
          path_in_repo: "docs/notes.txt",
          size: 5,
          sha256: "docs/notes.txt-sha256",
          chunks: []
        },
        {
          type: "add",
          path_in_repo: "docs/second.txt",
          size: 6,
          sha256: "docs/second.txt-sha256",
          chunks: []
        }
      ]
    });
    expect(uploadViewMocks.applyCommit).toHaveBeenCalledWith(
      {
        revision: "release/v1",
        parent_commit: "base-1",
        commit_message: "upload notes",
        operations: [
          {
            type: "add",
            path_in_repo: "docs/notes.txt",
            size: 5,
            sha256: "docs/notes.txt-sha256",
            chunks: []
          },
          {
            type: "add",
            path_in_repo: "docs/second.txt",
            size: 6,
            sha256: "docs/second.txt-sha256",
            chunks: []
          }
        ],
        upload_plan: {
          base_head: "base-1",
          statistics: {
            planned_upload_bytes: 11,
            copy_file_count: 0,
            chunk_fast_upload_file_count: 0
          },
          operations: [
            {
              index: 0,
              type: "add",
              strategy: "upload-full",
              field_name: "upload_file_0"
            },
            {
              index: 1,
              type: "add",
              strategy: "upload-full",
              field_name: "upload_file_1"
            }
          ]
        }
      },
      [
        {
          fieldName: "upload_file_0",
          file: firstFile,
          fileName: "notes.txt"
        },
        {
          fieldName: "upload_file_1",
          file: secondFile,
          fileName: "second.txt"
        }
      ],
      {
        onUploadProgress: expect.any(Function)
      }
    );
    expect(uploadViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });
    expect(uploadViewMocks.push).toHaveBeenLastCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });
  });

  it("surfaces stale plan errors with a refresh hint", async function testStalePlanError() {
    const file = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    uploadViewMocks.planCommit.mockRejectedValue(new Error("branch head changed after upload planning; please re-plan the upload"));

    const wrapper = mount(UploadView, {
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
    setInputFiles(inputElement, [file]);
    await input.trigger("change");
    await flushPromises();

    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(wrapper.text()).toContain("Repository changed during upload planning. Refresh the page and retry the upload.");
  });
});
