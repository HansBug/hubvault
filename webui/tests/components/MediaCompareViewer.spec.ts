import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import MediaCompareViewer from "@/components/MediaCompareViewer.vue";

describe("MediaCompareViewer", function suite() {
  it("renders side-by-side previews when both media revisions are available", function testComparisonRender() {
    const wrapper = mount(MediaCompareViewer, {
      props: {
        kind: "audio",
        oldMediaUrl: "/parent.wav",
        newMediaUrl: "/commit.wav",
        oldLabel: "Parent",
        newLabel: "Commit"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.find("[data-testid='media-compare-grid']").exists()).toBe(true);
    expect(wrapper.find("[data-testid='media-compare-single']").exists()).toBe(false);
    expect(wrapper.findAll("[data-testid='media-preview-card']")).toHaveLength(2);
    expect(wrapper.text()).toContain("Parent");
    expect(wrapper.text()).toContain("Commit");
  });

  it("renders a single preview card when only the new media is available", function testSingleRender() {
    const wrapper = mount(MediaCompareViewer, {
      props: {
        kind: "video",
        newMediaUrl: "/commit.mp4",
        newLabel: "Commit"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.find("[data-testid='media-compare-grid']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='media-compare-single']").exists()).toBe(true);
    expect(wrapper.findAll("[data-testid='media-preview-card']")).toHaveLength(1);
    expect(wrapper.find("video").attributes("src")).toBe("/commit.mp4");
    expect(wrapper.text()).toContain("Commit");
  });

  it("shows the unsupported preview state for avi compare entries", function testUnsupportedAviRender() {
    const wrapper = mount(MediaCompareViewer, {
      props: {
        kind: "video",
        oldMediaUrl: "/parent.avi",
        newMediaUrl: "/commit.avi",
        oldPath: "media/demo.avi",
        newPath: "media/demo.avi",
        oldDownloadUrl: "/download/parent.avi",
        newDownloadUrl: "/download/commit.avi",
        oldLabel: "Parent",
        newLabel: "Commit"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.findAll("[data-testid='media-preview-unavailable']")).toHaveLength(2);
    expect(wrapper.find("video").exists()).toBe(false);
    expect(wrapper.text()).toContain("AVI video preview is not available in this browser.");
  });
});
