<script setup>
import { formatBytes, formatRelativeDate } from "@/utils/format";

const props = defineProps({
  entries: {
    type: Array,
    default: function defaultEntries() {
      return [];
    }
  },
  selectedPath: {
    type: String,
    default: ""
  }
});

const emit = defineEmits(["open-folder", "open-file"]);

function displayName(path) {
  const parts = String(path || "").split("/");
  return parts[parts.length - 1] || path;
}

function handleOpen(row) {
  if (row.entry_type === "folder") {
    emit("open-folder", row.path);
  } else {
    emit("open-file", row.path);
  }
}

function rowClassName(row) {
  return row.row.path === props.selectedPath ? "is-current-row" : "";
}
</script>

<template>
  <el-table
    :data="entries"
    class="surface"
    row-key="path"
    :row-class-name="rowClassName"
    empty-text="No files under this path."
  >
    <el-table-column label="Path" min-width="280">
      <template #default="{ row }">
        <el-button link type="primary" @click="handleOpen(row)">
          <span class="table-path">
            <span class="table-path__kind">{{ row.entry_type === "folder" ? "dir" : "file" }}</span>
            <span>{{ displayName(row.path) }}</span>
          </span>
        </el-button>
      </template>
    </el-table-column>
    <el-table-column label="Last commit" min-width="220">
      <template #default="{ row }">
        <div>{{ row.last_commit?.title || "Unknown" }}</div>
      </template>
    </el-table-column>
    <el-table-column label="Updated" width="160">
      <template #default="{ row }">
        <span class="muted">{{ formatRelativeDate(row.last_commit?.date) }}</span>
      </template>
    </el-table-column>
    <el-table-column label="Size" width="120" align="right">
      <template #default="{ row }">
        <span>{{ row.entry_type === "file" ? formatBytes(row.size) : "-" }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>
