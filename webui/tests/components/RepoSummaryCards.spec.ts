import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RepoSummaryCards from "@/components/RepoSummaryCards.vue";

describe("RepoSummaryCards", function suite() {
  it("renders summary metrics from refs, commits, files, and storage", function testSummaryCards() {
    const wrapper = mount(RepoSummaryCards, {
      props: {
        refs: {
          branches: [{ name: "release/v1" }, { name: "dev" }],
          tags: [{ name: "v1.0" }]
        },
        filesCount: 14,
        commitsCount: 7,
        storageOverview: {
          total_size: 4096
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("Branches / Tags");
    expect(wrapper.text()).toContain("2 / 1");
    expect(wrapper.text()).toContain("14");
    expect(wrapper.text()).toContain("7");
    expect(wrapper.text()).toContain("4.0 KB");
  });
});
