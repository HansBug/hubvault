import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sliderSpy = vi.hoisted(function buildSliderSpy() {
  return vi.fn();
});

vi.mock("juxtaposejs/build/js/juxtapose", function mockJuxtaposeModule() {
  return {
    default: {}
  };
});

import ImageCompareViewer from "@/components/ImageCompareViewer.vue";

describe("ImageCompareViewer", function suite() {
  beforeEach(function resetJuxtapose() {
    sliderSpy.mockClear();
    (window as any).juxtapose = {
      JXSlider: sliderSpy
    };
  });

  it("creates a juxtapose slider against a generated selector host", async function testComparisonRender() {
    const wrapper = mount(ImageCompareViewer, {
      props: {
        oldImageUrl: "/old.svg",
        newImageUrl: "/new.svg",
        oldLabel: "Parent",
        newLabel: "Commit"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await vi.waitFor(function expectSlider() {
      expect(sliderSpy).toHaveBeenCalledTimes(1);
    });

    const [selector, images, options] = sliderSpy.mock.calls[0];
    expect(selector).toMatch(/^#image-compare-viewer-\d+$/);
    expect(wrapper.find(selector).exists()).toBe(true);
    expect(images).toEqual([
      {
        src: "/old.svg",
        label: "Parent"
      },
      {
        src: "/new.svg",
        label: "Commit"
      }
    ]);
    expect(options).toMatchObject({
      animate: false,
      showCredits: false,
      startingPosition: "50%"
    });
  });

  it("renders a single inline image when only one side is available", function testSingleImageRender() {
    const wrapper = mount(ImageCompareViewer, {
      props: {
        newImageUrl: "/new.svg",
        newLabel: "Commit"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.find("img").attributes("src")).toBe("/new.svg");
    expect(wrapper.text()).toContain("Commit");
    expect(sliderSpy).not.toHaveBeenCalled();
  });
});
