<script setup lang="ts">
import { computed } from "vue";
import {
  Document,
  Download,
  Files,
  Picture,
  Plus,
  Remove
} from "@element-plus/icons-vue";

import { buildBlobUrl, buildDownloadUrl } from "@/api/client";
import { isAudioPath, isImagePath, isVideoPath } from "@/utils/files";
import { formatBytes, shortOid } from "@/utils/format";
import HtmlDiffViewer from "./HtmlDiffViewer.vue";
import ImageCompareViewer from "./ImageCompareViewer.vue";
import MediaCompareViewer from "./MediaCompareViewer.vue";

const props = defineProps({
  change: {
    type: Object,
    required: true
  },
  commitId: {
    type: String,
    default: ""
  },
  compareParentCommitId: {
    type: String,
    default: ""
  }
});

const previewKind = computed(function resolvePreviewKind() {
  if (isImagePath(props.change.path)) {
    return "image";
  }
  if (isAudioPath(props.change.path)) {
    return "audio";
  }
  if (isVideoPath(props.change.path)) {
    return "video";
  }
  return "";
});

const isImageChange = computed(function resolveIsImageChange() {
  return previewKind.value === "image";
});
const mediaKind = computed(function resolveMediaKind() {
  return previewKind.value === "audio" || previewKind.value === "video" ? previewKind.value : "";
});

const showBinaryMetadata = computed(function resolveShowBinaryMetadata() {
  return Boolean(props.change.is_binary && !previewKind.value);
});

const changeTagType = computed(function resolveChangeTagType() {
  if (props.change.change_type === "added") {
    return "success";
  }
  if (props.change.change_type === "deleted") {
    return "danger";
  }
  return "primary";
});

const oldDownloadUrl = computed(function resolveOldDownloadUrl() {
  if (!props.change.old_file || !props.compareParentCommitId) {
    return "";
  }
  return buildDownloadUrl(props.compareParentCommitId, props.change.old_file.path);
});

const newDownloadUrl = computed(function resolveNewDownloadUrl() {
  if (!props.change.new_file || !props.commitId) {
    return "";
  }
  return buildDownloadUrl(props.commitId, props.change.new_file.path);
});

const oldBlobUrl = computed(function resolveOldBlobUrl() {
  if (!props.change.old_file || !props.compareParentCommitId) {
    return "";
  }
  return buildBlobUrl(props.compareParentCommitId, props.change.old_file.path);
});

const newBlobUrl = computed(function resolveNewBlobUrl() {
  if (!props.change.new_file || !props.commitId) {
    return "";
  }
  return buildBlobUrl(props.commitId, props.change.new_file.path);
});

const fileSummary = computed(function resolveFileSummary() {
  const parts = [];
  if (props.change.old_file && props.change.new_file) {
    parts.push(formatBytes(props.change.old_file.size) + " -> " + formatBytes(props.change.new_file.size));
  } else if (props.change.new_file) {
    parts.push(formatBytes(props.change.new_file.size));
  } else if (props.change.old_file) {
    parts.push(formatBytes(props.change.old_file.size));
  }
  if (previewKind.value) {
    parts.push(previewKind.value);
  } else if (props.change.is_binary) {
    parts.push("binary");
  } else {
    parts.push("text");
  }
  return parts.join(" · ");
});

function versionRows(fileVersion) {
  if (!fileVersion) {
    return [];
  }
  return [
    {
      label: "Size",
      value: formatBytes(fileVersion.size),
      mono: false
    },
    {
      label: "OID",
      value: shortOid(fileVersion.oid),
      mono: true
    },
    {
      label: "SHA-256",
      value: shortOid(fileVersion.sha256),
      mono: true
    }
  ];
}
</script>

<template>
  <el-card class="surface commit-change-card" body-style="padding: 20px;" data-testid="commit-change-card">
    <div class="surface__header commit-change-card__header">
      <div>
        <div class="commit-change-card__title">
          <el-icon><Document /></el-icon>
          <strong class="mono">{{ change.path }}</strong>
        </div>
        <p class="surface__subtitle">{{ fileSummary }}</p>
      </div>
      <div class="commit-change-card__actions">
        <el-tag :type="changeTagType" effect="plain">{{ change.change_type }}</el-tag>
        <el-button
          v-if="newDownloadUrl"
          :icon="Download"
          plain
          tag="a"
          :href="newDownloadUrl"
        >
          Download
        </el-button>
      </div>
    </div>

    <div v-if="showBinaryMetadata" class="commit-change-card__meta" data-testid="binary-metadata-panel">
      <div class="commit-change-card__side commit-change-card__side--compact">
        <div class="commit-change-card__side-title">
          <el-icon v-if="change.old_file"><Remove /></el-icon>
          <el-icon v-else><Files /></el-icon>
          <span>Before</span>
        </div>
        <div v-if="change.old_file" class="kv-list kv-list--compact">
          <div
            v-for="row in versionRows(change.old_file)"
            :key="'old-' + row.label"
            class="kv-row"
          >
            <span>{{ row.label }}</span>
            <strong :class="{ mono: row.mono }">{{ row.value }}</strong>
          </div>
          <el-button
            v-if="oldDownloadUrl"
            :icon="Download"
            plain
            tag="a"
            :href="oldDownloadUrl"
          >
            Download Old
          </el-button>
        </div>
        <div v-else class="commit-change-card__missing muted">Not present</div>
      </div>

      <div class="commit-change-card__side commit-change-card__side--compact">
        <div class="commit-change-card__side-title">
          <el-icon v-if="change.new_file"><Plus /></el-icon>
          <el-icon v-else><Files /></el-icon>
          <span>After</span>
        </div>
        <div v-if="change.new_file" class="kv-list kv-list--compact">
          <div
            v-for="row in versionRows(change.new_file)"
            :key="'new-' + row.label"
            class="kv-row"
          >
            <span>{{ row.label }}</span>
            <strong :class="{ mono: row.mono }">{{ row.value }}</strong>
          </div>
        </div>
        <div v-else class="commit-change-card__missing muted">Removed by this commit</div>
      </div>
    </div>

    <image-compare-viewer
      v-if="isImageChange"
      :old-image-url="oldBlobUrl"
      :new-image-url="newBlobUrl"
      old-label="Parent"
      new-label="Commit"
    />
    <media-compare-viewer
      v-else-if="mediaKind"
      :kind="mediaKind"
      :old-media-url="oldBlobUrl"
      :new-media-url="newBlobUrl"
      old-label="Parent"
      new-label="Commit"
    />
    <html-diff-viewer
      v-else-if="!change.is_binary"
      :diff-text="change.unified_diff || ''"
    />
    <el-empty v-else description="Binary file diff is not rendered inline. Compare metadata or download the file versions.">
      <template #image>
        <el-icon class="empty-icon"><Picture /></el-icon>
      </template>
    </el-empty>
  </el-card>
</template>
