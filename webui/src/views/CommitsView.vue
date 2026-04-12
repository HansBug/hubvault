<script setup lang="ts">
import { ref, watch } from "vue";

import { getCommits } from "@/api/client";
import CommitTimeline from "@/components/CommitTimeline.vue";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const loading = ref(false);
const error = ref("");
const commits = ref([]);

async function loadCommits() {
  loading.value = true;
  error.value = "";
  try {
    commits.value = await getCommits(props.revision, false);
  } catch (loadCommitsError) {
    error.value = loadCommitsError.message || "Unable to load commit history.";
    commits.value = [];
  } finally {
    loading.value = false;
  }
}

watch(
  function watchRevision() {
    return props.revision;
  },
  function refreshCommits() {
    loadCommits();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="commits-view">
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />
    <el-card class="surface" body-style="padding: 20px;">
      <div class="surface__header">
        <div>
          <h2 class="surface__title">Commits</h2>
          <p class="surface__subtitle">
            Reachable commit history for revision <strong>{{ props.revision }}</strong>.
          </p>
        </div>
      </div>
      <commit-timeline :commits="commits" :loading="loading" :revision="props.revision" />
    </el-card>
  </div>
</template>
