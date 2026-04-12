<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { Document } from "@element-plus/icons-vue";

import { highlightCodeElement, guessCodeLanguage } from "@/utils/syntax";

const props = defineProps({
  content: {
    type: String,
    default: ""
  },
  path: {
    type: String,
    default: ""
  },
  language: {
    type: String,
    default: ""
  },
  loading: {
    type: Boolean,
    default: false
  }
});

const codeElement = ref<HTMLElement | null>(null);

const resolvedLanguage = computed(function resolveLanguage() {
  return props.language || guessCodeLanguage(props.path);
});

const lineCount = computed(function resolveLineCount() {
  if (!props.content) {
    return 0;
  }
  return props.content.split("\n").length;
});

watch(
  function watchCodeInputs() {
    return [props.content, resolvedLanguage.value].join("\n--\n");
  },
  async function refreshHighlighting() {
    await nextTick();
    highlightCodeElement(codeElement.value);
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="code-viewer" data-testid="code-viewer">
    <div class="code-viewer__toolbar">
      <div class="code-viewer__language">
        <el-icon><Document /></el-icon>
        <span>{{ resolvedLanguage }}</span>
      </div>
      <span class="muted">{{ lineCount }} lines</span>
    </div>
    <el-skeleton v-if="loading" :rows="10" animated />
    <pre v-else class="code-viewer__pre line-numbers"><code
      ref="codeElement"
      :class="['code-viewer__code', 'language-' + resolvedLanguage]"
    >{{ content }}</code></pre>
  </div>
</template>
