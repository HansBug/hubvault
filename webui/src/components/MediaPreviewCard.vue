<script setup lang="ts">
import { computed } from "vue";

const props = defineProps({
  kind: {
    type: String,
    default: "audio"
  },
  src: {
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
</script>

<template>
  <div class="media-preview-card" data-testid="media-preview-card">
    <div class="media-preview-card__label">
      <span class="path-pill path-pill--compact">{{ label }}</span>
    </div>
    <div v-if="src" class="media-preview-card__body">
      <component
        :is="mediaTag"
        v-bind="mediaAttributes"
        :src="src"
        class="media-preview-card__player"
        :class="{ 'media-preview-card__player--video': isVideo }"
      />
    </div>
    <el-empty v-else :description="emptyText" />
  </div>
</template>
