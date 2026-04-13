import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import RefsPanel from "@/components/RefsPanel.vue";

function findButtonByText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().trim() === value;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("RefsPanel", function suite() {
  it("renders branch and tag buttons and emits the selected revision", async function testRefsSelection() {
    const wrapper = mount(RefsPanel, {
      props: {
        refs: {
          branches: [{ name: "main" }, { name: "dev" }],
          tags: [{ name: "v1.0" }]
        },
        currentRevision: "main"
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(findButtonByText(wrapper, "main").classes()).not.toContain("is-plain");
    expect(findButtonByText(wrapper, "dev").classes()).toContain("is-plain");

    await findButtonByText(wrapper, "dev").trigger("click");
    await findButtonByText(wrapper, "v1.0").trigger("click");

    expect(wrapper.emitted("select")).toEqual([["dev"], ["v1.0"]]);
  });

  it("tolerates null branch and tag collections", function testNullCollections() {
    const wrapper = mount(RefsPanel, {
      props: {
        refs: {
          branches: null,
          tags: null
        },
        currentRevision: ""
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.findAll("button")).toHaveLength(0);
    expect(wrapper.text()).toContain("Branches");
    expect(wrapper.text()).toContain("Tags");
  });
});
