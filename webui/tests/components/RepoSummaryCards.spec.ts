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

  it("falls back to zero counts and pending storage when summary data is absent", function testSummaryFallbacks() {
    const wrapper = mount(RepoSummaryCards, {
      props: {
        refs: null,
        filesCount: 0,
        commitsCount: 0,
        storageOverview: null
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("0 / 0");
    expect(wrapper.text()).toContain("Files");
    expect(wrapper.text()).toContain("Commits");
    expect(wrapper.text()).toContain("Pending");
  });
});
