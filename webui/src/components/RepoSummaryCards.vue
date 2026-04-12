<script setup lang="ts">
import { computed } from "vue";

import { formatBytes } from "@/utils/format";

const props = defineProps({
  refs: {
    type: Object,
    default: null
  },
  filesCount: {
    type: Number,
    default: 0
  },
  commitsCount: {
    type: Number,
    default: 0
  },
  storageOverview: {
    type: Object,
    default: null
  }
});

const cards = computed(function buildCards() {
  return [
    {
      label: "Branches / Tags",
      value: (props.refs?.branches?.length || 0) + " / " + (props.refs?.tags?.length || 0)
    },
    {
      label: "Files",
      value: String(props.filesCount || 0)
    },
    {
      label: "Commits",
      value: String(props.commitsCount || 0)
    },
    {
      label: "Storage",
      value: props.storageOverview ? formatBytes(props.storageOverview.total_size) : "Pending"
    }
  ];
});
</script>

<template>
  <div class="summary-grid">
    <el-card
      v-for="card in cards"
      :key="card.label"
      class="surface"
      body-style="padding: 18px;"
    >
      <div class="muted">{{ card.label }}</div>
      <div style="margin-top: 10px; font-size: 28px; font-weight: 700;">
        {{ card.value }}
      </div>
    </el-card>
  </div>
</template>
