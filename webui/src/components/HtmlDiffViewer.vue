<script setup lang="ts">
import { computed } from "vue";
import DOMPurify from "dompurify";
import { html as renderDiffHtml } from "diff2html";

const props = defineProps({
  diffText: {
    type: String,
    default: ""
  }
});

const renderedHtml = computed(function buildRenderedHtml() {
  if (!props.diffText) {
    return "";
  }
  return DOMPurify.sanitize(
    renderDiffHtml(props.diffText, {
      drawFileList: false,
      matching: "lines",
      outputFormat: "line-by-line",
      renderNothingWhenEmpty: false
    })
  );
});
</script>

<template>
  <el-empty
    v-if="!diffText"
    description="No inline text diff is available for this change."
  />
  <div
    v-else
    class="diff-viewer"
    data-testid="html-diff-viewer"
    v-html="renderedHtml"
  />
</template>
