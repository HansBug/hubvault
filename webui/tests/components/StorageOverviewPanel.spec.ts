import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import StorageOverviewPanel from "@/components/StorageOverviewPanel.vue";

describe("StorageOverviewPanel", function suite() {
  it("renders summary data and emits full verify requests", async function testStoragePanel() {
    const wrapper = mount(StorageOverviewPanel, {
      props: {
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

    await wrapper.get("button").trigger("click");

    expect(wrapper.text()).toContain("Run gc().");
    expect(wrapper.emitted("run-full-verify")).toHaveLength(1);
  });
});
