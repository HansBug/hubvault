import ElementPlus, { ElMessage, ElMessageBox } from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const storageViewMocks = vi.hoisted(function buildStorageViewMocks() {
  return {
    getStorageOverview: vi.fn(),
    runFullVerify: vi.fn(),
    runGc: vi.fn(),
    runQuickVerify: vi.fn(),
    runSquashHistory: vi.fn(),
    bootstrapSession: vi.fn()
  };
});

const sessionState = reactive({
  auth: null as any,
  refs: null as any
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    getStorageOverview: storageViewMocks.getStorageOverview,
    runFullVerify: storageViewMocks.runFullVerify,
    runGc: storageViewMocks.runGc,
    runQuickVerify: storageViewMocks.runQuickVerify,
    runSquashHistory: storageViewMocks.runSquashHistory
  };
});

vi.mock("@/stores/session", function mockSessionModule() {
  return {
    bootstrapSession: storageViewMocks.bootstrapSession,
    useSessionStore: function useSessionStore() {
      return {
        state: readonly(sessionState)
      };
    }
  };
});

import StorageView from "@/views/StorageView.vue";

function resetSessionState() {
  sessionState.auth = {
    access: "rw",
    can_write: true
  };
  sessionState.refs = {
    branches: [{ name: "release/v1" }, { name: "dev" }],
    tags: []
  };
}

function findButton(wrapper, label: string, index = 0) {
  const buttons = wrapper.findAll("button").filter(function findByText(item) {
    return item.text().trim() === label;
  });
  expect(buttons[index]).toBeTruthy();
  return buttons[index]!;
}

describe("StorageView", function suite() {
  beforeEach(function resetMocks() {
    vi.clearAllMocks();
    resetSessionState();
    storageViewMocks.getStorageOverview.mockResolvedValue({
      total_size: 4096,
      reachable_size: 3072,
      reclaimable_gc_size: 512,
      reclaimable_cache_size: 256,
      sections: [],
      recommendations: ["Run gc()."]
    });
    storageViewMocks.runQuickVerify.mockResolvedValue({
      ok: true,
      checked_refs: ["refs/heads/release/v1"],
      warnings: [],
      errors: []
    });
    storageViewMocks.runFullVerify.mockResolvedValue({
      ok: true,
      warnings: [],
      errors: []
    });
    storageViewMocks.runGc.mockResolvedValue({
      dry_run: true,
      reclaimed_size: 256,
      removed_file_count: 1
    });
    storageViewMocks.runSquashHistory.mockResolvedValue({
      ref_name: "release/v1",
      rewritten_commit_count: 3,
      dropped_ancestor_count: 2
    });
    vi.spyOn(ElMessage, "success").mockImplementation(function swallowSuccess() {
      return undefined as never;
    });
    vi.spyOn(ElMessageBox, "prompt").mockResolvedValue({ value: "Squash release/v1" } as never);
  });

  it("keeps storage analysis on demand and executes maintenance actions explicitly", async function testMaintenanceFlows() {
    const wrapper = mount(StorageView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(storageViewMocks.getStorageOverview).not.toHaveBeenCalled();
    expect(storageViewMocks.runQuickVerify).not.toHaveBeenCalled();
    expect(wrapper.get("[data-testid='storage-status-title']").text()).toBe("Storage analysis is on demand");

    await findButton(wrapper, "Load analysis").trigger("click");
    await flushPromises();

    expect(storageViewMocks.getStorageOverview).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("Run gc().");
    expect(wrapper.get("[data-testid='storage-status-title']").text()).toBe("Storage analysis ready");

    await findButton(wrapper, "Run now", 0).trigger("click");
    await flushPromises();

    expect(storageViewMocks.runQuickVerify).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain("Healthy");

    await findButton(wrapper, "Run now", 0).trigger("click");
    await flushPromises();

    expect(storageViewMocks.runFullVerify).toHaveBeenCalledTimes(1);

    await findButton(wrapper, "Preview GC").trigger("click");
    await flushPromises();

    expect(storageViewMocks.runGc).toHaveBeenCalledWith({
      dry_run: true,
      prune_cache: true
    });
    expect(storageViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });
    expect(storageViewMocks.getStorageOverview).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain("Latest GC Result");

    await findButton(wrapper, "Squash Current Branch").trigger("click");
    await flushPromises();

    expect(storageViewMocks.runSquashHistory).toHaveBeenCalledWith({
      ref_name: "release/v1",
      commit_message: "Squash release/v1",
      run_gc: false,
      prune_cache: false
    });
    expect(storageViewMocks.getStorageOverview).toHaveBeenCalledTimes(3);
    expect(wrapper.text()).toContain("Latest Squash Result");
  });
});
