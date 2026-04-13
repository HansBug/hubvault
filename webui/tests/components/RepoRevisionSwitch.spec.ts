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

  it("renders detached revisions with the fallback group and supports disabled mode", function testDetachedRevisionRendering() {
    const wrapper = mount(RepoRevisionSwitch, {
      props: {
        modelValue: "detached-commit",
        disabled: true
      },
      global: {
        stubs: {
          ElSelect: {
            name: "ElSelect",
            props: ["modelValue", "disabled"],
            template: [
              "<div",
              "  data-testid=\"revision-select\"",
              "  :data-model-value=\"modelValue\"",
              "  :data-disabled=\"String(disabled)\"",
              ">",
              "  <slot />",
              "</div>"
            ].join("")
          },
          ElOptionGroup: {
            props: ["label"],
            template: "<section class=\"option-group\"><h3>{{ label }}</h3><slot /></section>"
          },
          ElOption: {
            props: ["label", "value"],
            template: "<div class=\"option-item\" :data-value=\"value\">{{ label }}</div>"
          }
        }
      }
    });

    expect(wrapper.get("[data-testid='revision-select']").attributes("data-disabled")).toBe("true");
    expect(wrapper.text()).toContain("Branches");
    expect(wrapper.text()).toContain("Tags");
    expect(wrapper.text()).toContain("Selected Revision");
    expect(wrapper.text()).toContain("detached-commit");
  });

  it("does not duplicate known branch revisions in the detached group", function testKnownRevisionGroupOmission() {
    const wrapper = mount(RepoRevisionSwitch, {
      props: {
        modelValue: "main",
        refs: {
          branches: [{ name: "main" }],
          tags: [{ name: "v1.0" }]
        }
      },
      global: {
        stubs: {
          ElSelect: {
            name: "ElSelect",
            props: ["modelValue"],
            template: "<div data-testid=\"revision-select\" :data-model-value=\"modelValue\"><slot /></div>"
          },
          ElOptionGroup: {
            props: ["label"],
            template: "<section class=\"option-group\"><h3>{{ label }}</h3><slot /></section>"
          },
          ElOption: {
            props: ["label", "value"],
            template: "<div class=\"option-item\" :data-value=\"value\">{{ label }}</div>"
          }
        }
      }
    });

    expect(wrapper.text()).toContain("Branches");
    expect(wrapper.text()).toContain("Tags");
    expect(wrapper.text()).not.toContain("Selected Revision");
  });

  it("tolerates null branch and tag collections by falling back to empty lists", function testNullRefCollections() {
    const wrapper = mount(RepoRevisionSwitch, {
      props: {
        modelValue: "",
        refs: {
          branches: null,
          tags: null
        }
      },
      global: {
        stubs: {
          ElSelect: {
            name: "ElSelect",
            props: ["modelValue"],
            template: "<div data-testid=\"revision-select\" :data-model-value=\"modelValue\"><slot /></div>"
          },
          ElOptionGroup: {
            props: ["label"],
            template: "<section class=\"option-group\"><h3>{{ label }}</h3><slot /></section>"
          },
          ElOption: {
            props: ["label", "value"],
            template: "<div class=\"option-item\" :data-value=\"value\">{{ label }}</div>"
          }
        }
      }
    });

    expect(wrapper.text()).toContain("Branches");
    expect(wrapper.text()).toContain("Tags");
    expect(wrapper.findAll(".option-item")).toHaveLength(0);
  });

  it("accepts null refs from callers without crashing the rendered option groups", function testNullRefs() {
    const wrapper = mount(RepoRevisionSwitch, {
      props: {
        modelValue: "detached-commit",
        refs: null
      },
      global: {
        stubs: {
          ElSelect: {
            name: "ElSelect",
            props: ["modelValue"],
            template: "<div data-testid=\"revision-select\" :data-model-value=\"modelValue\"><slot /></div>"
          },
          ElOptionGroup: {
            props: ["label"],
            template: "<section class=\"option-group\"><h3>{{ label }}</h3><slot /></section>"
          },
          ElOption: {
            props: ["label", "value"],
            template: "<div class=\"option-item\" :data-value=\"value\">{{ label }}</div>"
          }
        }
      }
    });

    expect(wrapper.text()).toContain("Branches");
    expect(wrapper.text()).toContain("Tags");
    expect(wrapper.text()).toContain("Selected Revision");
    expect(wrapper.text()).toContain("detached-commit");
    expect(wrapper.findAll(".option-item")).toHaveLength(1);
  });
});
