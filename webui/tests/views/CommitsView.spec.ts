import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const commitsViewMocks = vi.hoisted(function buildCommitsViewMocks() {
  return {
    getCommits: vi.fn()
  };
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    getCommits: commitsViewMocks.getCommits
  };
});

vi.mock("@/components/CommitTimeline.vue", function mockCommitTimeline() {
  return {
    default: {
      props: ["commits", "loading", "revision"],
      template: "<div data-testid=\"commit-timeline\">{{ loading ? 'loading' : commits.length }}|{{ revision }}</div>"
    }
  };
});

import CommitsView from "@/views/CommitsView.vue";

const viewStubs = {
  ElAlert: {
    props: ["title"],
    template: "<div class=\"el-alert\">{{ title }}</div>"
  },
  ElCard: {
    template: "<div class=\"el-card\"><slot /></div>"
  }
};

describe("CommitsView", function suite() {
  it("loads commit history and refreshes when the revision changes", async function testCommitLoading() {
    commitsViewMocks.getCommits
      .mockResolvedValueOnce([{ commit_id: "1", title: "first" }])
      .mockRejectedValueOnce(new Error("history failed"));

    const wrapper = mount(CommitsView, {
      props: {
        revision: "release/v1"
      },
      global: {
        stubs: viewStubs
      }
    });

    await flushPromises();
    expect(commitsViewMocks.getCommits).toHaveBeenCalledWith("release/v1", false);
    expect(wrapper.get("[data-testid='commit-timeline']").text()).toBe("1|release/v1");

    await wrapper.setProps({
      revision: "dev"
    });
    await flushPromises();
    await flushPromises();

    expect(commitsViewMocks.getCommits).toHaveBeenCalledWith("dev", false);
    expect(wrapper.text()).toContain("history failed");
  });
});
