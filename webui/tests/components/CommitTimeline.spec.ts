import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import CommitTimeline from "@/components/CommitTimeline.vue";

describe("CommitTimeline", function suite() {
  it("renders loading, empty, and populated commit states", async function testCommitTimelineStates() {
    const wrapper = mount(CommitTimeline, {
      props: {
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
          created_at: "2026-04-12T00:00:00Z"
        }
      ]
    });

    expect(wrapper.text()).toContain("ship commit timeline");
    expect(wrapper.text()).toContain("details");
    expect(wrapper.html()).toContain("1234567890");
  });
});
