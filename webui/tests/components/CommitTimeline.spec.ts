import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

const commitTimelineMocks = vi.hoisted(function buildCommitTimelineMocks() {
  return {
    push: vi.fn()
  };
});

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRouter: function useRouter() {
      return {
        push: commitTimelineMocks.push
      };
    }
  };
});

import CommitTimeline from "@/components/CommitTimeline.vue";

function findButtonByText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(value) >= 0;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("CommitTimeline", function suite() {
  it("renders loading, empty, populated states, and opens commit details from the title", async function testCommitTimelineStates() {
    const wrapper = mount(CommitTimeline, {
      props: {
        revision: "release/v1",
        commits: [],
        loading: true
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.html()).toContain("el-skeleton");

    await wrapper.setProps({
      loading: false
    });
    expect(wrapper.text()).toContain("No commits available for this revision.");

    await wrapper.setProps({
      commits: [
        {
          commit_id: "1234567890abcdef1234567890abcdef12345678",
          title: "ship commit timeline",
          message: "details",
          authors: ["HubVault"],
          created_at: "2026-04-12T00:00:00Z"
        }
      ]
    });

    expect(wrapper.text()).toContain("ship commit timeline");
    expect(wrapper.text()).toContain("details");
    expect(wrapper.html()).toContain("1234567890");

    await findButtonByText(wrapper, "ship commit timeline").trigger("click");

    expect(commitTimelineMocks.push).toHaveBeenCalledWith({
      name: "commit-detail",
      params: {
        commitId: "1234567890abcdef1234567890abcdef12345678"
      },
      query: {
        revision: "release/v1"
      }
    });
  });
});
