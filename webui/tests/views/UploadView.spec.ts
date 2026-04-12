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
    uploadViewMocks.bootstrapSession.mockResolvedValue({
      repoRevision: "release/v1"
    });
    uploadViewMocks.buildExactUploadManifest.mockImplementation(async function buildManifest(entries, onProgress) {
      const totalBytes = entries.reduce(function accumulate(total, item) {
        return total + Number(item.file.size || 0);
      }, 0);
      if (typeof onProgress === "function" && entries.length) {
        onProgress({
          phase: "reading",
          currentPathInRepo: entries[0].pathInRepo,
          completedEntries: 0,
          totalEntries: entries.length,
          processedBytes: 0,
          totalBytes: totalBytes
        });
        onProgress({
          phase: "hashing",
          currentPathInRepo: entries[0].pathInRepo,
          completedEntries: 0,
          totalEntries: entries.length,
          processedBytes: Number(entries[0].file.size || 0),
          totalBytes: totalBytes
        });
        onProgress({
          phase: "completed",
          currentPathInRepo: entries[entries.length - 1].pathInRepo,
          completedEntries: entries.length,
          totalEntries: entries.length,
          processedBytes: totalBytes,
          totalBytes: totalBytes
        });
      }
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

  it("uses an auto-generated placeholder commit message when the upload form stays blank", async function testUploadQueue() {
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

    const autoMessage = "Upload docs/notes.txt, docs/second.txt (2 files, 11 B) with hubvault";
    const commitInput = wrapper.get("[data-testid='upload-commit-message-input']");

    expect((commitInput.element as HTMLInputElement).value).toBe("");
    expect(commitInput.attributes("placeholder")).toBe(autoMessage);

    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(uploadViewMocks.planCommit).toHaveBeenCalledWith({
      revision: "release/v1",
      commit_message: autoMessage,
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
        commit_message: autoMessage,
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
    expect(wrapper.get("[data-testid='upload-status-title']").text()).toBe("Upload interrupted");
  });

  it("keeps a successful upload as warning-only when the refresh step fails", async function testRefreshFailureWarning() {
    const file = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    uploadViewMocks.planCommit.mockResolvedValue({
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
    });
    uploadViewMocks.applyCommit.mockResolvedValue({
      oid: "upload-commit"
    });
    uploadViewMocks.bootstrapSession.mockRejectedValue(new Error("refresh temporarily unavailable"));

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

    expect(wrapper.get("[data-testid='upload-status-panel']").text()).toContain("Upload committed");
    expect(wrapper.get("[data-testid='upload-warning-alert']").text()).toContain("refresh temporarily unavailable");
    expect(wrapper.text()).toContain("No files are queued yet.");
    expect(uploadViewMocks.push).not.toHaveBeenCalled();
  });

  it("supports readonly sessions and back-to-files navigation", async function testReadonlyState() {
    sessionState.auth = {
      access: "ro",
      can_write: false
    };

    const wrapper = mount(UploadView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(wrapper.text()).toContain("Upload requires a read / write token.");
    await findButtonByText(wrapper, "Back to Files").trigger("click");

    expect(uploadViewMocks.push).toHaveBeenCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });
  });

  it("normalizes file targets, opens file and folder pickers, and supports clearing or removing queued entries", async function testQueueManagement() {
    uploadViewMocks.route.query = {
      path: "docs/config.json"
    };
    uploadViewMocks.getPathsInfo.mockResolvedValue([
      {
        path: "docs/config.json",
        entry_type: "file"
      }
    ]);

    const wrapper = mount(UploadView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    const fileInput = wrapper.get("[data-testid='upload-file-input']");
    const folderInput = wrapper.get("[data-testid='upload-folder-input']");
    const fileInputElement = fileInput.element as HTMLInputElement;
    const folderInputElement = folderInput.element as HTMLInputElement;
    const fileClickSpy = vi.spyOn(fileInputElement, "click");
    const folderClickSpy = vi.spyOn(folderInputElement, "click");
    const file = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    const folderFile = new File(["folder"], "demo.txt", {
      type: "text/plain"
    });

    Object.defineProperty(folderFile, "webkitRelativePath", {
      configurable: true,
      value: "nested/demo.txt"
    });

    expect(wrapper.get("[data-testid='upload-commit-message-input']").attributes("placeholder")).toBe(
      "Upload queued files to docs with hubvault"
    );

    await findButtonByText(wrapper, "Add Files").trigger("click");
    await findButtonByText(wrapper, "Add Folder").trigger("click");
    expect(fileClickSpy).toHaveBeenCalledTimes(1);
    expect(folderClickSpy).toHaveBeenCalledTimes(1);

    setInputFiles(fileInputElement, [file]);
    await fileInput.trigger("change");
    await flushPromises();
    expect(fileInputElement.value).toBe("");
    expect(wrapper.text()).toContain("docs/notes.txt");

    await findButtonByText(wrapper, "Clear").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("No files are queued yet.");

    setInputFiles(folderInputElement, [folderFile]);
    await folderInput.trigger("change");
    await flushPromises();
    expect(folderInputElement.value).toBe("");
    expect(wrapper.text()).toContain("docs/nested/demo.txt");

    await wrapper.get('button[aria-label="Remove queued file docs/nested/demo.txt"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("No files are queued yet.");
  });

  it("keeps users informed during zero-payload fast paths before the commit resolves", async function testZeroPayloadStatus() {
    const file = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    uploadViewMocks.planCommit.mockResolvedValue({
      base_head: "base-1",
      statistics: {
        planned_upload_bytes: 0,
        copy_file_count: 1,
        chunk_fast_upload_file_count: 1
      },
      operations: [
        {
          index: 0,
          type: "add",
          strategy: "chunk-fast"
        }
      ]
    });

    let resolveApplyCommit: (value: unknown) => void = function noop() {};
    uploadViewMocks.applyCommit.mockImplementation(function deferApply() {
      return new Promise(function waitForResolution(resolve) {
        resolveApplyCommit = resolve;
      });
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
    setInputFiles(input.element as HTMLInputElement, [file]);
    await input.trigger("change");
    await flushPromises();

    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();

    expect(uploadViewMocks.applyCommit).toHaveBeenCalledWith(
      expect.objectContaining({
        revision: "release/v1",
        parent_commit: "base-1"
      }),
      [],
      {
        onUploadProgress: expect.any(Function)
      }
    );
    expect(wrapper.get("[data-testid='upload-status-title']").text()).toBe("Finalizing commit");
    expect(wrapper.get("[data-testid='upload-status-message']").text()).toContain("No payload upload is required");
    expect(wrapper.get("[data-testid='upload-status-panel']").text()).toContain("No payload upload required");
    expect(wrapper.text()).toContain("1 copy fast paths");
    expect(wrapper.text()).toContain("1 chunk fast paths");

    resolveApplyCommit({
      oid: "upload-commit"
    });
    await flushPromises();
    await flushPromises();

    expect(uploadViewMocks.push).toHaveBeenLastCalledWith({
      name: "files",
      query: {
        revision: "release/v1",
        path: "docs"
      }
    });
  });

  it("updates upload progress callbacks and surfaces apply errors", async function testUploadProgressErrors() {
    const file = new File(["hello"], "notes.txt", {
      type: "text/plain"
    });
    uploadViewMocks.planCommit.mockResolvedValue({
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
    });
    uploadViewMocks.applyCommit.mockImplementation(async function applyWithProgress(_manifest, _uploads, options) {
      options.onUploadProgress({
        loaded: 2,
        total: 5
      });
      options.onUploadProgress({
        loaded: 5,
        total: 5
      });
      throw new Error("upload transport failed");
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
    setInputFiles(input.element as HTMLInputElement, [file]);
    await input.trigger("change");
    await flushPromises();

    await findButtonByText(wrapper, "Commit Queued Uploads").trigger("click");
    await flushPromises();
    await flushPromises();

    expect(uploadViewMocks.applyCommit).toHaveBeenCalled();
    expect(wrapper.get("[data-testid='upload-status-title']").text()).toBe("Upload interrupted");
    expect(wrapper.get("[data-testid='upload-status-message']").text()).toContain("upload transport failed");
    expect(wrapper.text()).toContain("upload transport failed");
    expect(uploadViewMocks.bootstrapSession).not.toHaveBeenCalled();
  });

  it("shows workspace preparation errors when the upload destination cannot be resolved", async function testWorkspaceErrors() {
    uploadViewMocks.route.query = {
      path: "broken/path"
    };
    uploadViewMocks.getPathsInfo.mockRejectedValueOnce(new Error("workspace unavailable"));

    const wrapper = mount(UploadView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(wrapper.text()).toContain("workspace unavailable");
  });
});
