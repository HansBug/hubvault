<script setup>
import { computed } from "vue";

import { buildDownloadUrl } from "@/api/client";
import { formatBytes, formatDateTime, shortOid } from "@/utils/format";
import ReadmeViewer from "./ReadmeViewer.vue";

const props = defineProps({
  entry: {
    type: Object,
    default: null
  },
  content: {
    type: String,
    default: ""
  },
  loading: {
    type: Boolean,
    default: false
  },
  previewMode: {
    type: String,
    default: "empty"
  },
  revision: {
    type: String,
    default: ""
  }
});

const downloadUrl = computed(function buildUrl() {
  if (!props.entry || props.entry.entry_type !== "file") {
    return "";
  }
  return buildDownloadUrl(props.revision, props.entry.path);
});
</script>

<template>
  <el-card class="surface" body-style="padding: 20px;" data-testid="file-preview-panel">
    <div class="surface__header">
      <div>
        <h3 class="surface__title">Preview</h3>
        <p class="surface__subtitle">
          {{ entry?.path || "Select a file from the table to preview its content." }}
        </p>
      </div>
      <el-button
        v-if="downloadUrl"
        tag="a"
        :href="downloadUrl"
        plain
      >
        Download
      </el-button>
    </div>

    <div v-if="entry" class="kv-list" style="margin-bottom: 18px;">
      <div class="kv-row">
        <span>Type</span>
        <strong>{{ entry.entry_type }}</strong>
      </div>
      <div class="kv-row" v-if="entry.entry_type === 'file'">
        <span>Size</span>
        <strong>{{ formatBytes(entry.size) }}</strong>
      </div>
      <div class="kv-row">
        <span>Last commit</span>
        <strong>
          {{ entry.last_commit?.title || "Unknown" }}
          <span v-if="entry.last_commit" class="muted">({{ shortOid(entry.last_commit.oid) }})</span>
        </strong>
      </div>
      <div class="kv-row">
        <span>Updated at</span>
        <strong>{{ formatDateTime(entry.last_commit?.date) }}</strong>
      </div>
    </div>

    <div class="preview-panel__content">
      <readme-viewer
        v-if="previewMode === 'markdown'"
        :path="entry?.path"
        :content="content"
        :loading="loading"
        empty-title="No preview yet"
      />
      <el-skeleton v-else-if="loading" :rows="8" animated />
      <pre v-else-if="previewMode === 'text' || previewMode === 'json'" class="preview-panel__text">{{ content }}</pre>
      <el-empty
        v-else-if="previewMode === 'binary'"
        description="This file is treated as binary or too large for inline preview."
      />
      <el-empty
        v-else
        description="Select a text-like file to preview, or download binary content directly."
      />
    </div>
  </el-card>
</template>
