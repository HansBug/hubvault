import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import App from "@/App.vue";

describe("App", function suite() {
  it("renders the router outlet", function testRouterViewOutlet() {
    const wrapper = mount(App, {
      global: {
        stubs: {
          RouterView: {
            template: "<main data-test='router-outlet'>router outlet</main>"
          }
        }
      }
    });

    expect(wrapper.get("[data-test='router-outlet']").text()).toBe("router outlet");
  });
});
