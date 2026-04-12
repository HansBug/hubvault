<script setup lang="ts">
import {
  Delete,
  Document,
  Download,
  FolderOpened,
  View
} from "@element-plus/icons-vue";

import { buildDownloadUrl } from "@/api/client";
import { formatBytes, formatRelativeDate } from "@/utils/format";

const props = defineProps({
  entries: {
    type: Array,
    default: function defaultEntries() {
      return [];
    }
  },
  revision: {
    type: String,
    default: ""
  },
  canWrite: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(["open-folder", "open-file", "open-commit", "delete-entry"]);

function displayName(path) {
  const parts = String(path || "").split("/");
  return parts[parts.length - 1] || path;
}

function downloadUrl(path) {
  return buildDownloadUrl(props.revision, path);
}

function openEntry(row) {
  emit(row.entry_type === "folder" ? "open-folder" : "open-file", row.path);
}

function openCommit(row) {
  if (row && row.last_commit && row.last_commit.oid) {
    emit("open-commit", row.last_commit.oid);
  }
}
</script>

<template>
  <el-table
    :data="entries"
    class="surface"
    row-key="path"
    empty-text="No files under this path."
  >
    <el-table-column label="Name" min-width="320">
      <template #default="{ row }">
        <el-button
          link
          type="primary"
          @click="openEntry(row)"
        >
          <span class="table-path">
            <el-icon class="table-path__icon">
              <folder-opened v-if="row.entry_type === 'folder'" />
              <document v-else />
            </el-icon>
            <span>{{ displayName(row.path) }}</span>
          </span>
        </el-button>
      </template>
    </el-table-column>
    <el-table-column label="Last Commit" min-width="240">
      <template #default="{ row }">
        <el-button
          v-if="row.last_commit?.oid"
          link
          type="primary"
          class="table-commit-link"
          @click="openCommit(row)"
        >
          {{ row.last_commit.title || "Unknown" }}
        </el-button>
        <div v-else>Unknown</div>
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
    <el-table-column label="Actions" width="190" align="right">
      <template #default="{ row }">
        <div class="table-actions">
          <el-tooltip :content="row.entry_type === 'folder' ? 'Open folder' : 'Open file'" placement="top">
            <el-button
              :icon="View"
              circle
              plain
              :aria-label="row.entry_type === 'folder' ? 'Open folder ' + row.path : 'Open file ' + row.path"
              @click="openEntry(row)"
            />
          </el-tooltip>
          <el-tooltip v-if="row.entry_type === 'file'" content="Download file" placement="top">
            <el-button
              :icon="Download"
              circle
              plain
              tag="a"
              :href="downloadUrl(row.path)"
              :aria-label="'Download ' + row.path"
            />
          </el-tooltip>
          <el-tooltip v-if="canWrite" content="Delete entry" placement="top">
            <el-button
              :icon="Delete"
              circle
              plain
              type="danger"
              :aria-label="'Delete ' + row.path"
              @click="$emit('delete-entry', row)"
            />
          </el-tooltip>
        </div>
      </template>
    </el-table-column>
  </el-table>
</template>
