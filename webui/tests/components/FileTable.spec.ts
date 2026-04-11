import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import FileTable from "@/components/FileTable.vue";

const ElTableStub = {
  props: ["data", "rowClassName"],
  provide() {
    return {
      tableRows: this.data,
      tableRowClassName: this.rowClassName
    };
  },
  template: "<div class=\"el-table-stub\"><slot /></div>"
};

const ElTableColumnStub = {
  inject: ["tableRows", "tableRowClassName"],
  template: [
    "<div class=\"el-table-column-stub\">",
    "  <div",
    "    v-for=\"row in tableRows\"",
    "    :key=\"row.path\"",
    "    :class=\"tableRowClassName ? tableRowClassName({ row: row }) : ''\"",
    "  >",
    "    <slot :row=\"row\" />",
    "  </div>",
    "</div>"
  ].join("")
};

function findButtonByText(wrapper, text: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(text) >= 0;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("FileTable", function suite() {
  it("renders entries, highlights the selected row, and emits open events", async function testFileTable() {
    const wrapper = mount(FileTable, {
      props: {
        selectedPath: "docs/readme.md",
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
          ElTable: ElTableStub,
          ElTableColumn: ElTableColumnStub,
          ElButton: {
            template: "<button @click=\"$emit('click')\"><slot /></button>"
          }
        }
      }
    });

    await findButtonByText(wrapper, "docs").trigger("click");
    await findButtonByText(wrapper, "readme.md").trigger("click");

    expect(wrapper.emitted("open-folder")).toContainEqual(["docs"]);
    expect(wrapper.emitted("open-file")).toContainEqual(["docs/readme.md"]);
    expect(wrapper.text()).toContain("update docs");
    expect(wrapper.text()).toContain("add readme");
    expect(wrapper.text()).toContain("dir");
    expect(wrapper.text()).toContain("file");
    expect(wrapper.html()).toContain("is-current-row");
  });
});
