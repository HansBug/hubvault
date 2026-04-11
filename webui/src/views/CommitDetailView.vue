<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Back, Clock, Tickets } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { getCommitDetail } from "@/api/client";
import CommitChangeCard from "@/components/CommitChangeCard.vue";
import { formatDateTime, shortOid } from "@/utils/format";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const route = useRoute();
const router = useRouter();

const loading = ref(false);
const error = ref("");
const detail = ref<any>(null);

const commitId = computed(function resolveCommitId() {
  return typeof route.params.commitId === "string" ? route.params.commitId : "";
});

const changeSummary = computed(function resolveChangeSummary() {
  const summary = {
    added: 0,
    deleted: 0,
    modified: 0
  };
  const changes = detail.value && Array.isArray(detail.value.changes) ? detail.value.changes : [];
  changes.forEach(function accumulate(change) {
    if (change.change_type === "added") {
      summary.added += 1;
    } else if (change.change_type === "deleted") {
      summary.deleted += 1;
    } else {
      summary.modified += 1;
    }
  });
  return summary;
});

async function loadCommitDetail() {
  if (!commitId.value) {
    detail.value = null;
    error.value = "Missing commit identifier.";
    return;
  }

  loading.value = true;
  error.value = "";
  try {
    detail.value = await getCommitDetail(commitId.value, true);
  } catch (loadDetailError) {
    error.value = loadDetailError.message || "Unable to load commit detail.";
    detail.value = null;
  } finally {
    loading.value = false;
  }
}

function backToCommits() {
  router.push({
    name: "commits",
    query: {
      revision: props.revision
    }
  });
}

watch(
  function watchCommitInputs() {
    return [props.revision, commitId.value].join(":");
  },
  function refreshCommitDetail() {
    loadCommitDetail();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="commit-detail-view">
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />

    <el-card class="surface" body-style="padding: 22px;">
      <div class="surface__header">
        <div>
          <div class="detail-heading">
            <el-icon><Tickets /></el-icon>
            <h2 class="surface__title">Commit Detail</h2>
          </div>
          <p class="surface__subtitle">
            First-parent diff view for commit <strong class="mono">{{ shortOid(commitId) }}</strong>.
          </p>
        </div>
        <el-button :icon="Back" plain @click="backToCommits">
          Back to Commits
        </el-button>
      </div>

      <el-skeleton v-if="loading" :rows="10" animated />
      <div v-else-if="detail" class="stack">
        <div class="detail-hero">
          <div class="stack">
            <h3 class="detail-hero__title">{{ detail.commit.title }}</h3>
            <p v-if="detail.commit.message" class="detail-hero__message">{{ detail.commit.message }}</p>
            <div class="app-shell__meta">
              <span class="path-pill">
                <el-icon><Clock /></el-icon>
                {{ formatDateTime(detail.commit.created_at) }}
              </span>
              <span class="path-pill">commit: <span class="mono">{{ shortOid(detail.commit.commit_id) }}</span></span>
              <span class="path-pill" v-if="detail.compare_parent_commit_id">
                parent: <span class="mono">{{ shortOid(detail.compare_parent_commit_id) }}</span>
              </span>
            </div>
          </div>

          <div class="summary-grid detail-hero__stats">
            <el-card class="surface" body-style="padding: 16px;">
              <div class="metric-card__label">Added</div>
              <div class="metric-card__value">{{ changeSummary.added }}</div>
            </el-card>
            <el-card class="surface" body-style="padding: 16px;">
              <div class="metric-card__label">Modified</div>
              <div class="metric-card__value">{{ changeSummary.modified }}</div>
            </el-card>
            <el-card class="surface" body-style="padding: 16px;">
              <div class="metric-card__label">Deleted</div>
              <div class="metric-card__value">{{ changeSummary.deleted }}</div>
            </el-card>
            <el-card class="surface" body-style="padding: 16px;">
              <div class="metric-card__label">Parents</div>
              <div class="metric-card__value">{{ detail.parent_commit_ids.length }}</div>
            </el-card>
          </div>
        </div>

        <el-empty
          v-if="!detail.changes.length"
          description="This commit does not change any reachable files."
        />
        <commit-change-card
          v-for="change in detail.changes"
          :key="change.path"
          :change="change"
          :commit-id="detail.commit.commit_id"
          :compare-parent-commit-id="detail.compare_parent_commit_id || ''"
        />
      </div>
    </el-card>
  </div>
</template>
