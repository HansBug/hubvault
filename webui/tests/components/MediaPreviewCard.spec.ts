import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import MediaPreviewCard from "@/components/MediaPreviewCard.vue";

describe("MediaPreviewCard", function suite() {
  it("shows a download fallback for avi videos that browsers do not preview inline", function testUnsupportedAviPreview() {
    const wrapper = mount(MediaPreviewCard, {
      props: {
        kind: "video",
        src: "/api/v1/content/blob/media/demo.avi?revision=release%2Fv1",
        path: "media/demo.avi",
        downloadUrl: "/api/v1/content/download/media/demo.avi?revision=release%2Fv1",
        label: "media/demo.avi"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.find("video").exists()).toBe(false);
    expect(wrapper.get("[data-testid='media-preview-unavailable']").text()).toContain(
      "AVI video preview is not available in this browser."
    );
    expect(wrapper.get("[data-testid='media-preview-download']").attributes("href")).toContain(
      "/api/v1/content/download/media/demo.avi"
    );
  });

  it("falls back to the unavailable state after a runtime video loading error", async function testRuntimePreviewFailure() {
    const wrapper = mount(MediaPreviewCard, {
      props: {
        kind: "video",
        src: "/api/v1/content/blob/media/demo.mp4?revision=release%2Fv1",
        path: "media/demo.mp4",
        downloadUrl: "/api/v1/content/download/media/demo.mp4?revision=release%2Fv1",
        label: "media/demo.mp4"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.get("video").attributes("src")).toContain("/api/v1/content/blob/media/demo.mp4");

    await wrapper.get("video").trigger("error");

    expect(wrapper.find("video").exists()).toBe(false);
    expect(wrapper.get("[data-testid='media-preview-unavailable']").text()).toContain(
      "This video could not be rendered inline."
    );
  });
});
