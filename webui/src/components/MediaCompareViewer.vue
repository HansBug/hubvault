<script setup lang="ts">
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
  oldLabel: {
    type: String,
    default: "Before"
  },
  newLabel: {
    type: String,
    default: "After"
  }
});
</script>

<template>
  <div class="media-compare-viewer" data-testid="media-compare-viewer">
    <div class="media-compare-viewer__grid">
      <media-preview-card
        :kind="props.kind"
        :src="oldMediaUrl"
        :label="oldLabel"
        empty-text="Not present in the parent revision."
      />
      <media-preview-card
        :kind="props.kind"
        :src="newMediaUrl"
        :label="newLabel"
        empty-text="Not present in this commit."
      />
    </div>
  </div>
</template>
