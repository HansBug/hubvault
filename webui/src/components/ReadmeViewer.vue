<script setup>
import { computed } from "vue";
import DOMPurify from "dompurify";
import MarkdownIt from "markdown-it";

import { isMarkdownPath } from "@/utils/files";

const props = defineProps({
  path: {
    type: String,
    default: ""
  },
  content: {
    type: String,
    default: ""
  },
  loading: {
    type: Boolean,
    default: false
  },
  emptyTitle: {
    type: String,
    default: "Nothing to render"
  },
  emptyDescription: {
    type: String,
    default: "This view does not have README content yet."
  }
});

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true
});

const renderedHtml = computed(function buildRenderedHtml() {
  if (!props.content || !isMarkdownPath(props.path)) {
    return "";
  }
  return DOMPurify.sanitize(markdown.render(props.content));
});
</script>

<template>
  <el-skeleton v-if="loading" :rows="8" animated />
  <el-empty
    v-else-if="!content"
    :description="emptyDescription"
  >
    <template #image>
      <div style="font-size: 44px;">#</div>
    </template>
    <div>{{ emptyTitle }}</div>
  </el-empty>
  <article
    v-else-if="isMarkdownPath(path)"
    class="markdown-body"
    v-html="renderedHtml"
  />
  <pre v-else class="preview-panel__text">{{ content }}</pre>
</template>
