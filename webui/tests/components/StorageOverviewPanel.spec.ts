import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import StorageOverviewPanel from "@/components/StorageOverviewPanel.vue";

function findButton(wrapper, label: string) {
  const button = wrapper.findAll("button").find(function findByLabel(item) {
    return item.text().trim() === label;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("StorageOverviewPanel", function suite() {
  it("renders lightweight summary cards and emits storage actions", async function testStoragePanel() {
    const wrapper = mount(StorageOverviewPanel, {
      props: {
        summary: {
          total_size: 4096,
          total_file_count: 12,
          metadata_size: 512,
          metadata_file_count: 3,
          branch_count: 2,
          tag_count: 1
        },
        overview: {
          total_size: 4096,
          reachable_size: 2048,
          reclaimable_gc_size: 512,
          reclaimable_cache_size: 1024,
          sections: [
            {
              name: "cache",
              path: "cache/",
              total_size: 1024,
              reclaimable_size: 1024,
              reclaim_strategy: "prune-cache"
            }
          ],
          recommendations: ["Run gc()."]
        },
        quickVerify: {
          ok: true,
          checked_refs: ["refs/heads/main"],
          warnings: [],
          errors: []
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(wrapper, "Refresh analysis").trigger("click");
    await findButton(wrapper, "Run again").trigger("click");
    await findButton(wrapper, "Run now").trigger("click");

    expect(wrapper.text()).toContain("4.0 KB");
    expect(wrapper.text()).toContain("12");
    expect(wrapper.text()).toContain("512 B");
    expect(wrapper.text()).toContain("Run gc().");
    expect(wrapper.emitted("load-overview")).toHaveLength(1);
    expect(wrapper.emitted("run-quick-verify")).toHaveLength(1);
    expect(wrapper.emitted("run-full-verify")).toHaveLength(1);
  });
});
