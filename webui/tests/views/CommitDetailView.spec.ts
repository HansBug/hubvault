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
});
