import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RepoRevisionSwitch from "@/components/RepoRevisionSwitch.vue";

describe("RepoRevisionSwitch", function suite() {
  it("emits the selected revision when the select updates", async function testSelectEmit() {
    const wrapper = mount(RepoRevisionSwitch, {
      props: {
        modelValue: "main",
        refs: {
          branches: [{ name: "main" }, { name: "release/v1" }],
          tags: [{ name: "v1.0" }]
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    wrapper.findComponent({ name: "ElSelect" }).vm.$emit("update:modelValue", "release/v1");

    expect(wrapper.emitted("update:modelValue")[0]).toEqual(["release/v1"]);
  });
});
