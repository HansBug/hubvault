import ElementPlus from "element-plus";
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";

const sliderSpy = vi.hoisted(function buildSliderSpy() {
  return vi.fn();
});
const juxtaposeModuleState = vi.hoisted(function buildJuxtaposeModuleState() {
  return {
    default: {}
  };
});

vi.mock("juxtaposejs/build/js/juxtapose", function mockJuxtaposeModule() {
  return juxtaposeModuleState;
});

import ImageCompareViewer from "@/components/ImageCompareViewer.vue";

describe("ImageCompareViewer", function suite() {
  beforeEach(function resetJuxtapose() {
    sliderSpy.mockClear();
    juxtaposeModuleState.default = {};
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

  it("falls back to the old image label when only the parent side exists", function testOldOnlyImageRender() {
    const wrapper = mount(ImageCompareViewer, {
      props: {
        oldImageUrl: "/old.svg",
        oldLabel: "Parent"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.find("img").attributes("src")).toBe("/old.svg");
    expect(wrapper.text()).toContain("Parent");
    expect(sliderSpy).not.toHaveBeenCalled();
  });

  it("uses the imported juxtapose module when the runtime is not attached to window", async function testModuleFallback() {
    (window as any).juxtapose = undefined;
    juxtaposeModuleState.default = {
      JXSlider: sliderSpy
    };

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

    expect(wrapper.find("img").exists()).toBe(false);
  });

  it("falls back to the raw imported module object when it exposes the slider constructor directly", async function testModuleObjectFallback() {
    (window as any).juxtapose = undefined;
    juxtaposeModuleState.default = undefined as any;
    (juxtaposeModuleState as any).JXSlider = sliderSpy;

    mount(ImageCompareViewer, {
      props: {
        oldImageUrl: "/old.svg",
        newImageUrl: "/new.svg"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    await flushPromises();
    await vi.waitFor(function expectSlider() {
      expect(sliderSpy).toHaveBeenCalledTimes(1);
    });

    delete (juxtaposeModuleState as any).JXSlider;
  });

  it("falls back to an inline preview when the compare runtime is unavailable", async function testFallbackWithoutSlider() {
    (window as any).juxtapose = undefined;

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

    expect(wrapper.find("img").attributes("src")).toBe("/new.svg");
    expect(wrapper.text()).toContain("Commit");
    expect(sliderSpy).not.toHaveBeenCalled();
  });
});
