<script setup lang="ts">
import {
  Delete,
  Document,
  Download,
  Files,
  FolderOpened,
  Headset,
  VideoPlay,
  View
} from "@element-plus/icons-vue";
import { Icon } from "@iconify/vue";

import { buildDownloadUrl } from "@/api/client";
import { materialFileIcons } from "@/icons/materialFileIcons";
import { formatBytes, formatRelativeDate } from "@/utils/format";
import { getFileIconMeta } from "@/utils/fileIcons";

const FALLBACK_ICONS = {
  audio: Headset,
  binary: Files,
  folder: FolderOpened,
  video: VideoPlay
};

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

function entryVisual(row) {
  return getFileIconMeta(row.path, row.entry_type);
}

function fallbackIcon(row) {
  const visual = entryVisual(row);
  return FALLBACK_ICONS[visual.icon] || Document;
}

function materialIcon(row) {
  const visual = entryVisual(row);
  return materialFileIcons[visual.icon] || materialFileIcons.document;
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
          class="table-path__button"
          :data-file-kind="entryVisual(row).kind"
          @click="openEntry(row)"
        >
          <span class="table-path" :data-file-kind="entryVisual(row).kind">
            <span
              class="table-path__icon"
              :class="'table-path__icon--' + entryVisual(row).tone"
              :data-file-icon="entryVisual(row).icon"
              :data-icon-source="entryVisual(row).source"
            >
              <el-icon v-if="entryVisual(row).source === 'element'" class="table-path__glyph">
                <component :is="fallbackIcon(row)" />
              </el-icon>
              <icon v-else class="table-path__glyph" :icon="materialIcon(row)" />
            </span>
            <span class="table-path__label">{{ displayName(row.path) }}</span>
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
