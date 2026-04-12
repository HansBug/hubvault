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

function findButtonByLabelOrText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(value) >= 0 || item.attributes("aria-label") === value;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe("FileTable", function suite() {
  it("renders entries, commit links, and action buttons with download links", async function testFileTable() {
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
              oid: "commit-docs",
              title: "update docs",
              date: "2026-04-12T00:00:00Z"
            }
          },
          {
            path: "docs/readme.md",
            entry_type: "file",
            size: 1024,
            last_commit: {
              oid: "commit-readme",
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
          ElTooltip: {
            template: "<span class=\"el-tooltip-stub\"><slot /></span>"
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

    await findButtonByLabelOrText(wrapper, "docs").trigger("click");
    await findButtonByLabelOrText(wrapper, "readme.md").trigger("click");
    await findButtonByLabelOrText(wrapper, "update docs").trigger("click");
    await findButtonByLabelOrText(wrapper, "Open folder docs").trigger("click");
    await findButtonByLabelOrText(wrapper, "Delete docs/readme.md").trigger("click");

    expect(wrapper.emitted("open-folder")).toContainEqual(["docs"]);
    expect(wrapper.emitted("open-file")).toContainEqual(["docs/readme.md"]);
    expect(wrapper.emitted("open-commit")).toContainEqual(["commit-docs"]);
    expect(wrapper.emitted("delete-entry")).toHaveLength(1);
    expect(wrapper.text()).toContain("update docs");
    expect(wrapper.text()).toContain("add readme");
    expect(wrapper.html()).toContain("Download docs/readme.md");
    expect(wrapper.html()).toContain("/api/v1/content/download/docs/readme.md?revision=release%2Fv1");
  });
});
