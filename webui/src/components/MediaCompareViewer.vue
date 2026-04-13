<script setup lang="ts">
import { computed } from "vue";

import MediaPreviewCard from "./MediaPreviewCard.vue";

const props = defineProps({
  kind: {
    type: String,
    default: "audio"
  },
  oldMediaUrl: {
    type: String,
    default: ""
  },
  newMediaUrl: {
    type: String,
    default: ""
  },
  oldPath: {
    type: String,
    default: ""
  },
  newPath: {
    type: String,
    default: ""
  },
  oldDownloadUrl: {
    type: String,
    default: ""
  },
  newDownloadUrl: {
    type: String,
    default: ""
  },
  oldLabel: {
    type: String,
    default: "Before"
  },
  newLabel: {
    type: String,
    default: "After"
  }
});

const hasComparison = computed(function resolveHasComparison() {
  return Boolean(props.oldMediaUrl && props.newMediaUrl);
});
const singleMediaUrl = computed(function resolveSingleMediaUrl() {
  return props.newMediaUrl || props.oldMediaUrl;
});
const singleLabel = computed(function resolveSingleLabel() {
  return props.newMediaUrl ? props.newLabel : props.oldLabel;
});
const singlePath = computed(function resolveSinglePath() {
  return props.newMediaUrl ? props.newPath : props.oldPath;
});
const singleDownloadUrl = computed(function resolveSingleDownloadUrl() {
  return props.newMediaUrl ? props.newDownloadUrl : props.oldDownloadUrl;
});
const singleEmptyText = computed(function resolveSingleEmptyText() {
  return props.newMediaUrl ? "Not present in the parent revision." : "Not present in this commit.";
});
</script>

<template>
  <div class="media-compare-viewer" data-testid="media-compare-viewer">
    <div v-if="hasComparison" class="media-compare-viewer__grid" data-testid="media-compare-grid">
      <media-preview-card
        :kind="props.kind"
        :src="oldMediaUrl"
        :path="oldPath"
        :download-url="oldDownloadUrl"
        :label="oldLabel"
        empty-text="Not present in the parent revision."
      />
      <media-preview-card
        :kind="props.kind"
        :src="newMediaUrl"
        :path="newPath"
        :download-url="newDownloadUrl"
        :label="newLabel"
        empty-text="Not present in this commit."
      />
    </div>
    <div v-else class="media-compare-viewer__single" data-testid="media-compare-single">
      <media-preview-card
        :kind="props.kind"
        :src="singleMediaUrl"
        :path="singlePath"
        :download-url="singleDownloadUrl"
        :label="singleLabel"
        :empty-text="singleEmptyText"
      />
    </div>
  </div>
</template>
