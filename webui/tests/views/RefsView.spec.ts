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

    expect(wrapper.get("[data-testid='refs-action-create-branch']").text()).toContain("New Branch");
    expect(wrapper.get("[data-testid='refs-action-create-tag']").text()).toContain("New Tag");
    expect(wrapper.get("[data-testid='refs-action-merge']").text()).toContain("Merge Into Current");

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

  it("creates tags, switches revisions from the panel, and deletes the current tag", async function testTagActions() {
    vi.spyOn(ElMessageBox, "prompt").mockResolvedValue({ value: "v2.0" } as never);

    const wrapper = mount(RefsView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(wrapper, "New Tag").trigger("click");
    await flushPromises();

    expect(refsViewMocks.createTagRef).toHaveBeenCalledWith({
      tag: "v2.0",
      revision: "release/v1"
    });
    expect(refsViewMocks.bootstrapSession).toHaveBeenCalledWith("release/v1", { force: true });

    await findButton(wrapper, "dev").trigger("click");
    expect(refsViewMocks.push).toHaveBeenLastCalledWith({
      name: "refs",
      query: {
        revision: "dev"
      }
    });

    await findButton(wrapper, "v1.0").trigger("click");
    expect(refsViewMocks.push).toHaveBeenLastCalledWith({
      name: "refs",
      query: {
        revision: "v1.0"
      }
    });

    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);
    const tagWrapper = mount(RefsView, {
      props: {
        revision: "v1.0"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(tagWrapper, "Delete Current").trigger("click");
    await flushPromises();

    expect(refsViewMocks.deleteTagRef).toHaveBeenCalledWith("v1.0");
    expect(refsViewMocks.push).toHaveBeenLastCalledWith({
      name: "refs",
      query: {
        revision: "release/v1"
      }
    });
  });

  it("keeps cancelled actions silent and surfaces write failures", async function testActionErrors() {
    const promptSpy = vi.spyOn(ElMessageBox, "prompt");
    promptSpy
      .mockRejectedValueOnce("cancel" as never)
      .mockResolvedValueOnce({ value: "v2.1" } as never)
      .mockResolvedValueOnce({ value: "feature/slow" } as never)
      .mockResolvedValueOnce({ value: "base-commit" } as never);
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValueOnce("close" as never);

    refsViewMocks.createTagRef.mockRejectedValueOnce(new Error("tag create failed"));
    refsViewMocks.mergeRevision.mockRejectedValueOnce(new Error("merge failed"));
    refsViewMocks.resetBranchRef.mockRejectedValueOnce(new Error("reset failed"));

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
    expect(refsViewMocks.createBranchRef).not.toHaveBeenCalled();

    await findButton(wrapper, "New Tag").trigger("click");
    await flushPromises();
    expect(refsViewMocks.createTagRef).toHaveBeenCalledWith({
      tag: "v2.1",
      revision: "release/v1"
    });
    expect(wrapper.text()).toContain("tag create failed");

    await findButton(wrapper, "Merge Into Current").trigger("click");
    await flushPromises();
    expect(refsViewMocks.mergeRevision).toHaveBeenCalledWith({
      source_revision: "feature/slow",
      target_revision: "release/v1"
    });
    expect(wrapper.text()).toContain("merge failed");

    await findButton(wrapper, "Reset Current").trigger("click");
    await flushPromises();
    expect(refsViewMocks.resetBranchRef).toHaveBeenCalledWith({
      ref_name: "release/v1",
      to_revision: "base-commit"
    });
    expect(wrapper.text()).toContain("reset failed");

    await findButton(wrapper, "Delete Current").trigger("click");
    await flushPromises();
    expect(refsViewMocks.deleteBranchRef).not.toHaveBeenCalled();
  });

  it("hides write actions for readonly sessions and disables branch-only actions on tag revisions", function testReadonlyAndTagStates() {
    sessionState.auth = {
      access: "ro",
      can_write: false
    };

    const readonlyWrapper = mount(RefsView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(readonlyWrapper.find("[data-testid='refs-action-create-branch']").exists()).toBe(false);
    expect(readonlyWrapper.find("[data-testid='refs-action-create-tag']").exists()).toBe(false);

    resetSessionState();
    const tagWrapper = mount(RefsView, {
      props: {
        revision: "v1.0"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(tagWrapper.get("[data-testid='refs-action-merge']").attributes("disabled")).toBeDefined();
    expect(tagWrapper.get("[data-testid='refs-action-reset']").attributes("disabled")).toBeDefined();
    expect(tagWrapper.get("[data-testid='refs-action-delete']").attributes("disabled")).toBeUndefined();
  });

  it("surfaces default write failure messages and falls back tag deletion to main when no default branch exists", async function testRefFallbackBranches() {
    vi.spyOn(ElMessageBox, "prompt")
      .mockResolvedValueOnce({ value: "feature/no-message" } as never)
      .mockResolvedValueOnce({ value: "v3.0" } as never)
      .mockResolvedValueOnce({ value: "dev" } as never)
      .mockResolvedValueOnce({ value: "base-commit" } as never);
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);

    refsViewMocks.createBranchRef.mockRejectedValueOnce({});
    refsViewMocks.createTagRef.mockRejectedValueOnce({});
    refsViewMocks.mergeRevision.mockRejectedValueOnce({});
    refsViewMocks.resetBranchRef.mockRejectedValueOnce({});
    refsViewMocks.deleteBranchRef.mockRejectedValueOnce({});

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
    expect(wrapper.text()).toContain("Unable to create the branch.");

    await findButton(wrapper, "New Tag").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Unable to create the tag.");

    await findButton(wrapper, "Merge Into Current").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Unable to merge the source revision.");

    await findButton(wrapper, "Reset Current").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Unable to reset the current branch.");

    await findButton(wrapper, "Delete Current").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Unable to delete the current reference.");

    resetSessionState();
    sessionState.service = {
      repo: {
        default_branch: ""
      }
    };
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(undefined as never);

    const tagWrapper = mount(RefsView, {
      props: {
        revision: "v1.0"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(tagWrapper, "Delete Current").trigger("click");
    await flushPromises();

    expect(refsViewMocks.deleteTagRef).toHaveBeenCalledWith("v1.0");
    expect(refsViewMocks.bootstrapSession).toHaveBeenCalledWith("main", { force: true });
    expect(refsViewMocks.push).toHaveBeenLastCalledWith({
      name: "refs",
      query: {
        revision: "main"
      }
    });
  });

  it("renders empty ref collections safely and leaves branch-only actions disabled when nothing matches", function testEmptyRefCollections() {
    sessionState.refs = null;

    const wrapper = mount(RefsView, {
      props: {
        revision: "detached"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.get("[data-testid='refs-action-merge']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-testid='refs-action-reset']").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-testid='refs-action-delete']").attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("Current: detached");
  });

  it("passes through blank prompt payloads and treats cancel-or-close prompt exits as no-ops", async function testPromptBranches() {
    vi.spyOn(ElMessageBox, "prompt")
      .mockResolvedValueOnce({ value: "" } as never)
      .mockResolvedValueOnce({ value: "" } as never)
      .mockResolvedValueOnce({ value: "" } as never)
      .mockResolvedValueOnce({ value: "" } as never);

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
    await findButton(wrapper, "New Tag").trigger("click");
    await flushPromises();
    await findButton(wrapper, "Merge Into Current").trigger("click");
    await flushPromises();
    await findButton(wrapper, "Reset Current").trigger("click");
    await flushPromises();

    expect(refsViewMocks.createBranchRef).toHaveBeenCalledWith({
      branch: "",
      revision: "release/v1"
    });
    expect(refsViewMocks.createTagRef).toHaveBeenCalledWith({
      tag: "",
      revision: "release/v1"
    });
    expect(refsViewMocks.mergeRevision).toHaveBeenCalledWith({
      source_revision: "",
      target_revision: "release/v1"
    });
    expect(refsViewMocks.resetBranchRef).toHaveBeenCalledWith({
      ref_name: "release/v1",
      to_revision: ""
    });

    vi.spyOn(ElMessageBox, "prompt")
      .mockRejectedValueOnce("close" as never)
      .mockRejectedValueOnce("cancel" as never)
      .mockRejectedValueOnce("close" as never)
      .mockRejectedValueOnce("cancel" as never);

    const silentWrapper = mount(RefsView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(silentWrapper, "New Tag").trigger("click");
    await flushPromises();
    await findButton(silentWrapper, "Merge Into Current").trigger("click");
    await flushPromises();
    await findButton(silentWrapper, "Reset Current").trigger("click");
    await flushPromises();
    await findButton(silentWrapper, "New Branch").trigger("click");
    await flushPromises();

    expect(refsViewMocks.createTagRef).toHaveBeenCalledTimes(1);
    expect(refsViewMocks.mergeRevision).toHaveBeenCalledTimes(1);
    expect(refsViewMocks.resetBranchRef).toHaveBeenCalledTimes(1);
    expect(refsViewMocks.createBranchRef).toHaveBeenCalledTimes(1);
  });
});
