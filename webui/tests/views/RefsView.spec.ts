import ElementPlus, { ElMessage, ElMessageBox } from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const refsViewMocks = vi.hoisted(function buildRefsViewMocks() {
  return {
    createBranchRef: vi.fn(),
    createTagRef: vi.fn(),
    deleteBranchRef: vi.fn(),
    deleteTagRef: vi.fn(),
    mergeRevision: vi.fn(),
    resetBranchRef: vi.fn(),
    bootstrapSession: vi.fn(),
    push: vi.fn()
  };
});

const sessionState = reactive({
  auth: null as any,
  refs: null as any,
  service: null as any
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    createBranchRef: refsViewMocks.createBranchRef,
    createTagRef: refsViewMocks.createTagRef,
    deleteBranchRef: refsViewMocks.deleteBranchRef,
    deleteTagRef: refsViewMocks.deleteTagRef,
    mergeRevision: refsViewMocks.mergeRevision,
    resetBranchRef: refsViewMocks.resetBranchRef
  };
});

vi.mock("@/stores/session", function mockSessionModule() {
  return {
    bootstrapSession: refsViewMocks.bootstrapSession,
    useSessionStore: function useSessionStore() {
      return {
        state: readonly(sessionState)
      };
    }
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRouter: function useRouter() {
      return {
        push: refsViewMocks.push
      };
    }
  };
});

import RefsView from "@/views/RefsView.vue";

function resetSessionState() {
  sessionState.auth = {
    access: "rw",
    can_write: true
  };
  sessionState.refs = {
    branches: [{ name: "release/v1" }, { name: "dev" }],
    tags: [{ name: "v1.0" }]
  };
  sessionState.service = {
    repo: {
      default_branch: "release/v1"
    }
  };
}

function findButton(wrapper, label: string) {
  const button = wrapper.findAll("button").find(function findByText(item) {
    return item.text().trim() === label;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("RefsView", function suite() {
  beforeEach(function resetMocks() {
    vi.clearAllMocks();
    resetSessionState();
    refsViewMocks.createBranchRef.mockResolvedValue({ ok: true });
    refsViewMocks.createTagRef.mockResolvedValue({ ok: true });
    refsViewMocks.deleteBranchRef.mockResolvedValue({ ok: true });
    refsViewMocks.deleteTagRef.mockResolvedValue({ ok: true });
    refsViewMocks.mergeRevision.mockResolvedValue({
      status: "merged",
      target_revision: "release/v1",
      source_revision: "dev",
      conflicts: []
    });
    refsViewMocks.resetBranchRef.mockResolvedValue({
      oid: "reset-commit"
    });
    vi.spyOn(ElMessage, "success").mockImplementation(function swallowSuccess() {
      return undefined as never;
    });
  });

  it("creates a branch and renders the latest merge result", async function testCreateAndMerge() {
    vi.spyOn(ElMessageBox, "prompt")
      .mockResolvedValueOnce({ value: "feature/ui" } as never)
      .mockResolvedValueOnce({ value: "dev" } as never);

    const wrapper = mount(RefsView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(wrapper, "New Branch").trigger("click");
    await flushPromises();

    expect(refsViewMocks.createBranchRef).toHaveBeenCalledWith({
      branch: "feature/ui",
      revision: "release/v1"
    });
    expect(refsViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });

    await findButton(wrapper, "Merge Into Current").trigger("click");
    await flushPromises();

    expect(refsViewMocks.mergeRevision).toHaveBeenCalledWith({
      source_revision: "dev",
      target_revision: "release/v1"
    });
    expect(wrapper.text()).toContain("Latest Merge Result");
    expect(wrapper.text()).toContain("merged");
  });

  it("resets and deletes the current branch", async function testResetAndDelete() {
    vi.spyOn(ElMessageBox, "prompt").mockResolvedValue({ value: "v1.0" } as never);
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);

    const wrapper = mount(RefsView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(wrapper, "Reset Current").trigger("click");
    await flushPromises();

    expect(refsViewMocks.resetBranchRef).toHaveBeenCalledWith({
      ref_name: "release/v1",
      to_revision: "v1.0"
    });
    expect(refsViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });

    await findButton(wrapper, "Delete Current").trigger("click");
    await flushPromises();

    expect(refsViewMocks.deleteBranchRef).toHaveBeenCalledWith("release/v1");
    expect(refsViewMocks.push).toHaveBeenCalledWith({
      name: "refs",
      query: {
        revision: "release/v1"
      }
    });
  });
});
