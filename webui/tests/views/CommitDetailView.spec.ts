import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const commitDetailMocks = vi.hoisted(function buildCommitDetailMocks() {
  return {
    route: {
      params: {
        commitId: "commit-2"
      }
    },
    push: vi.fn(),
    getCommitDetail: vi.fn()
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRoute: function useRoute() {
      return commitDetailMocks.route;
    },
    useRouter: function useRouter() {
      return {
        push: commitDetailMocks.push
      };
    }
  };
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    getCommitDetail: commitDetailMocks.getCommitDetail
  };
});

vi.mock("@/components/CommitChangeCard.vue", function mockCommitChangeCard() {
  return {
    default: {
      props: ["change", "commitId", "compareParentCommitId"],
      template: "<div data-testid='commit-change-card-stub'>{{ change.path }}|{{ commitId }}|{{ compareParentCommitId }}</div>"
    }
  };
});

import CommitDetailView from "@/views/CommitDetailView.vue";

describe("CommitDetailView", function suite() {
  beforeEach(function resetCommitDetailMocks() {
    vi.clearAllMocks();
    commitDetailMocks.getCommitDetail.mockResolvedValue({
      commit: {
        commit_id: "commit-2",
        title: "update docs",
        message: "body",
        created_at: "2026-04-12T00:00:00Z"
      },
      parent_commit_ids: ["commit-1"],
      compare_parent_commit_id: "commit-1",
      changes: [
        {
          path: "docs/guide.md",
          change_type: "modified",
          is_binary: false,
          unified_diff: "diff --git a/docs/guide.md b/docs/guide.md\n",
          old_file: null,
          new_file: null
        }
      ]
    });
  });

  it("loads commit detail, renders compact summary cards, and routes back to the commit list", async function testCommitDetail() {
    const wrapper = mount(CommitDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(commitDetailMocks.getCommitDetail).toHaveBeenCalledWith("commit-2", true);
    expect(wrapper.text()).toContain("update docs");
    expect(wrapper.text()).toContain("body");
    expect(wrapper.findAll(".commit-detail-pill")).toHaveLength(3);
    expect(wrapper.findAll(".metric-card--inline")).toHaveLength(4);
    expect(wrapper.get("[data-testid='commit-change-card-stub']").text()).toContain("docs/guide.md|commit-2|commit-1");

    const button = wrapper.findAll("button").find(function findMatch(item) {
      return item.text().indexOf("Back to Commits") >= 0;
    });
    expect(button).toBeTruthy();
    await button!.trigger("click");

    expect(commitDetailMocks.push).toHaveBeenCalledWith({
      name: "commits",
      query: {
        revision: "release/v1"
      }
    });
  });

  it("summarizes added, modified, and deleted changes while hiding optional commit fields", async function testCommitSummaryBranches() {
    commitDetailMocks.getCommitDetail.mockResolvedValueOnce({
      commit: {
        commit_id: "commit-3",
        title: "reshape tree",
        message: "",
        created_at: "2026-04-12T00:00:00Z"
      },
      parent_commit_ids: [],
      compare_parent_commit_id: "",
      changes: [
        { path: "docs/new.md", change_type: "added", is_binary: false },
        { path: "docs/guide.md", change_type: "modified", is_binary: false },
        { path: "docs/old.md", change_type: "deleted", is_binary: false }
      ]
    });

    const wrapper = mount(CommitDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(wrapper.text()).toContain("Added");
    expect(wrapper.text()).toContain("Modified");
    expect(wrapper.text()).toContain("Deleted");
    expect(wrapper.find(".detail-hero__message").exists()).toBe(false);
    expect(wrapper.findAll(".commit-detail-pill")).toHaveLength(2);
    expect(wrapper.findAll("[data-testid='commit-change-card-stub']")).toHaveLength(3);
  });

  it("shows empty and error states for missing or unreadable commit details", async function testCommitDetailErrors() {
    commitDetailMocks.route.params.commitId = 42 as any;

    const missingWrapper = mount(CommitDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(commitDetailMocks.getCommitDetail).not.toHaveBeenCalled();
    expect(missingWrapper.text()).toContain("Missing commit identifier.");
    expect((missingWrapper.vm as any).changeSummary).toEqual({
      added: 0,
      deleted: 0,
      modified: 0
    });

    commitDetailMocks.route.params.commitId = "commit-4";
    commitDetailMocks.getCommitDetail.mockRejectedValueOnce({});

    const errorWrapper = mount(CommitDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(errorWrapper.text()).toContain("Unable to load commit detail.");
  });

  it("renders the empty reachable-files state when a commit has no visible changes", async function testEmptyChangeState() {
    commitDetailMocks.route.params.commitId = "commit-5";
    commitDetailMocks.getCommitDetail.mockResolvedValueOnce({
      commit: {
        commit_id: "commit-5",
        title: "metadata only",
        message: "no file changes",
        created_at: "2026-04-12T00:00:00Z"
      },
      parent_commit_ids: ["commit-4"],
      compare_parent_commit_id: "commit-4",
      changes: []
    });

    const wrapper = mount(CommitDetailView, {
      props: {
        revision: "release/v1"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();

    expect(wrapper.text()).toContain("This commit does not change any reachable files.");
    expect(wrapper.find("[data-testid='commit-change-card-stub']").exists()).toBe(false);
  });
});
