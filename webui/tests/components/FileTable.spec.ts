import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import FileTable from "@/components/FileTable.vue";

const ElTableStub = {
  props: ["data"],
  provide() {
    return {
      tableRows: this.data
    };
  },
  template: "<div class=\"el-table-stub\"><slot /></div>"
};

const ElTableColumnStub = {
  inject: ["tableRows"],
  template: [
    "<div class=\"el-table-column-stub\">",
    "  <div v-for=\"row in tableRows\" :key=\"row.path\">",
    "    <slot :row=\"row\" />",
    "  </div>",
    "</div>"
  ].join("")
};

function findButtons(wrapper, text: string) {
  return wrapper.findAll("button").filter(function findMatch(item) {
    return item.text().indexOf(text) >= 0 || item.attributes("aria-label") === text;
  });
}

describe("FileTable", function suite() {
  it("renders entries and emits open and delete events with download links", async function testFileTable() {
    const wrapper = mount(FileTable, {
      props: {
        revision: "release/v1",
        canWrite: true,
        entries: [
          {
            path: "docs",
            entry_type: "folder",
            size: 0,
            last_commit: {
              title: "update docs",
              date: "2026-04-12T00:00:00Z"
            }
          },
          {
            path: "docs/readme.md",
            entry_type: "file",
            size: 1024,
            last_commit: {
              title: "add readme",
              date: "2026-04-12T00:00:00Z"
            }
          }
        ]
      },
      global: {
        stubs: {
          ElIcon: {
            template: "<span class=\"el-icon\"><slot /></span>"
          },
          ElTable: ElTableStub,
          ElTableColumn: ElTableColumnStub,
          ElButton: {
            props: ["href", "ariaLabel", "tag"],
            emits: ["click"],
            template: "<button :aria-label=\"ariaLabel\" :data-href=\"href\" @click=\"$emit('click')\"><slot /></button>"
          }
        }
      }
    });

    await findButtons(wrapper, "docs")[0].trigger("click");
    await findButtons(wrapper, "readme.md")[0].trigger("click");
    await findButtons(wrapper, "Delete docs")[0].trigger("click");
    await findButtons(wrapper, "Delete docs/readme.md")[0].trigger("click");

    expect(wrapper.emitted("open-folder")).toContainEqual(["docs"]);
    expect(wrapper.emitted("open-file")).toContainEqual(["docs/readme.md"]);
    expect(wrapper.emitted("delete-entry")).toHaveLength(2);
    expect(wrapper.text()).toContain("update docs");
    expect(wrapper.text()).toContain("add readme");
    expect(wrapper.html()).toContain("Download docs/readme.md");
    expect(wrapper.html()).toContain("/api/v1/content/download/docs/readme.md?revision=release%2Fv1");
  });
});
