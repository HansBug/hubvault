<script setup lang="ts">
import { formatDateTime, formatRelativeDate, shortOid } from "@/utils/format";

defineProps({
  commits: {
    type: Array,
    default: function defaultCommits() {
      return [];
    }
  },
  loading: {
    type: Boolean,
    default: false
  }
});
</script>

<template>
  <el-skeleton v-if="loading" :rows="8" animated />
  <el-empty
    v-else-if="!commits.length"
    description="No commits available for this revision."
  />
  <el-timeline v-else>
    <el-timeline-item
      v-for="commit in commits"
      :key="commit.commit_id"
      :timestamp="formatRelativeDate(commit.created_at)"
      placement="top"
      type="primary"
    >
      <div class="timeline-card">
        <div class="timeline-card__title">
          <strong>{{ commit.title }}</strong>
          <span class="mono muted">{{ shortOid(commit.commit_id) }}</span>
        </div>
        <div class="muted">{{ formatDateTime(commit.created_at) }}</div>
        <p v-if="commit.message" style="margin: 12px 0 0; white-space: pre-wrap;">
          {{ commit.message }}
        </p>
      </div>
    </el-timeline-item>
  </el-timeline>
</template>
