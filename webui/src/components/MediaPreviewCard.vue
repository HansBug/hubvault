<script setup lang="ts">
import { Download } from "@element-plus/icons-vue";
import { computed, ref, watch } from "vue";

import { isKnownUnsupportedBrowserVideoPath } from "@/utils/files";

const props = defineProps({
  kind: {
    type: String,
    default: "audio"
  },
  src: {
    type: String,
    default: ""
  },
  path: {
    type: String,
    default: ""
  },
  downloadUrl: {
    type: String,
    default: ""
  },
  label: {
    type: String,
    default: "Preview"
  },
  emptyText: {
    type: String,
    default: "Media preview is not available."
  }
});

const isVideo = computed(function resolveIsVideo() {
  return props.kind === "video";
});
const mediaTag = computed(function resolveMediaTag() {
  return isVideo.value ? "video" : "audio";
});
const loadFailed = ref(false);
const knownUnsupportedVideo = computed(function resolveKnownUnsupportedVideo() {
  return isVideo.value && isKnownUnsupportedBrowserVideoPath(props.path);
});
const showUnavailableState = computed(function resolveShowUnavailableState() {
  return Boolean(props.src) && (knownUnsupportedVideo.value || loadFailed.value);
});
const unavailableTitle = computed(function resolveUnavailableTitle() {
  if (knownUnsupportedVideo.value) {
    return "AVI video preview is not available in this browser.";
  }
  if (isVideo.value) {
    return "This video could not be rendered inline.";
  }
  return "This media file could not be rendered inline.";
});
const unavailableHint = computed(function resolveUnavailableHint() {
  if (knownUnsupportedVideo.value) {
    return "Download the file to inspect it locally, or convert it to a browser-friendly format first.";
  }
  return "Download the file to inspect it locally.";
});
const mediaAttributes = computed(function resolveMediaAttributes() {
  if (isVideo.value) {
    return {
      controls: true,
      preload: "metadata",
      playsinline: true
    };
  }
  return {
    controls: true,
    preload: "metadata"
  };
});

function handleMediaError() {
  loadFailed.value = true;
}

function clearMediaError() {
  loadFailed.value = false;
}

watch(
  function watchMediaSource() {
    return [props.kind, props.path, props.src].join(":");
  },
  function resetMediaError() {
    loadFailed.value = false;
  }
);
</script>

<template>
  <div class="media-preview-card" data-testid="media-preview-card">
    <div class="media-preview-card__label">
      <span class="path-pill path-pill--compact">{{ label }}</span>
    </div>
    <div v-if="showUnavailableState" class="media-preview-card__fallback" data-testid="media-preview-unavailable">
      <el-alert
        type="warning"
        :closable="false"
        :title="unavailableTitle"
        show-icon
      />
      <p class="media-preview-card__hint muted">{{ unavailableHint }}</p>
      <el-button
        v-if="downloadUrl"
        data-testid="media-preview-download"
        :icon="Download"
        plain
        tag="a"
        :href="downloadUrl"
      >
        Download
      </el-button>
    </div>
    <div v-else-if="src" class="media-preview-card__body">
      <component
        :is="mediaTag"
        v-bind="mediaAttributes"
        :src="src"
        class="media-preview-card__player"
        :class="{ 'media-preview-card__player--video': isVideo }"
        @canplay="clearMediaError"
        @error="handleMediaError"
        @loadedmetadata="clearMediaError"
      />
    </div>
    <el-empty v-else :description="emptyText" />
  </div>
</template>
