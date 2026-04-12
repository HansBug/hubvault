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
  it("renders lightweight summary cards and keeps heavy metrics hidden until analysis is loaded", async function testSummaryPanel() {
    const wrapper = mount(StorageOverviewPanel, {
      props: {
        summary: {
          total_size: 4096,
          total_file_count: 12,
          metadata_size: 512,
          metadata_file_count: 3,
          branch_count: 2,
          tag_count: 1
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(wrapper, "Refresh").trigger("click");
    await findButton(wrapper, "Load analysis").trigger("click");

    expect(wrapper.text()).toContain("4.0 KB");
    expect(wrapper.text()).toContain("12");
    expect(wrapper.text()).toContain("512 B");
    expect(wrapper.text()).not.toContain("Reachable");
    expect(wrapper.emitted("refresh-summary")).toHaveLength(1);
    expect(wrapper.emitted("load-overview")).toHaveLength(1);
  });

  it("shows the analysis strip only after overview data is available", async function testAnalysisPanel() {
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

    expect(wrapper.get("[data-testid='storage-analysis-strip']").text()).toContain("Reachable");
    expect(wrapper.get("[data-testid='storage-analysis-strip']").text()).toContain("2.0 KB");
    expect(wrapper.text()).toContain("Run gc().");
    expect(wrapper.emitted("load-overview")).toHaveLength(1);
    expect(wrapper.emitted("run-quick-verify")).toHaveLength(1);
    expect(wrapper.emitted("run-full-verify")).toHaveLength(1);
  });

  it("renders loading placeholders and disables actions when background work is running", function testLoadingStates() {
    const wrapper = mount(StorageOverviewPanel, {
      props: {
        loadingSummary: true,
        loadingOverview: true,
        loadingQuickVerify: true,
        loadingFullVerify: true,
        actionsDisabled: true
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("Loading...");
    expect(findButton(wrapper, "Refresh").attributes("disabled")).toBeDefined();
    expect(findButton(wrapper, "Load analysis").attributes("disabled")).toBeDefined();
    expect(findButton(wrapper, "Run now").attributes("disabled")).toBeDefined();
  });

  it("renders failed full verification and empty recommendation states", async function testFullVerifyBranches() {
    const wrapper = mount(StorageOverviewPanel, {
      props: {
        summary: {
          total_size: 8192,
          total_file_count: 24,
          metadata_size: 1024
        },
        overview: {
          total_size: 8192,
          reachable_size: 4096,
          reclaimable_gc_size: 1024,
          reclaimable_cache_size: 0,
          sections: [],
          recommendations: []
        },
        fullVerify: {
          ok: false,
          warnings: ["pack missing checksum"],
          errors: ["missing chunk", "broken ref"]
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await findButton(wrapper, "Refresh analysis").trigger("click");
    await findButton(wrapper, "Run again").trigger("click");

    expect(wrapper.text()).toContain("Issues found");
    expect(wrapper.text()).toContain("Warnings");
    expect(wrapper.text()).toContain("1");
    expect(wrapper.text()).toContain("Errors");
    expect(wrapper.text()).toContain("2");
    expect(wrapper.text()).toContain("No storage recommendations at the moment.");
    expect(wrapper.emitted("load-overview")).toHaveLength(1);
    expect(wrapper.emitted("run-full-verify")).toHaveLength(1);
  });
});
