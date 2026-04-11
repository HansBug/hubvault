<script setup lang="ts">
import { Connection, Right } from "@element-plus/icons-vue";
import { useRouter } from "vue-router";

import { formatDateTime, formatRelativeDate, shortOid } from "@/utils/format";

const props = defineProps({
  commits: {
    type: Array,
    default: function defaultCommits() {
      return [];
    }
  },
  loading: {
    type: Boolean,
    default: false
  },
  revision: {
    type: String,
    default: ""
  }
});

const router = useRouter();

function openCommit(commitId) {
  router.push({
    name: "commit-detail",
    params: {
      commitId: commitId
    },
    query: {
      revision: props.revision
    }
  });
}
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
        <div class="timeline-card__meta">
          <div class="muted">{{ formatDateTime(commit.created_at) }}</div>
          <el-button
            :icon="Right"
            plain
            @click="openCommit(commit.commit_id)"
          >
            View Diff
          </el-button>
        </div>
        <p v-if="commit.message" class="timeline-card__message">
          {{ commit.message }}
        </p>
        <div class="timeline-card__chips">
          <span class="path-pill">
            <el-icon><Connection /></el-icon>
            {{ commit.authors?.join(", ") || "HubVault" }}
          </span>
        </div>
      </div>
    </el-timeline-item>
  </el-timeline>
</template>
