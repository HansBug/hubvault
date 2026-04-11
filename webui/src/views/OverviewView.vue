<script setup>
import { ref, watch } from "vue";

import { getBlobBytes, getCommits, getRepoFiles, getStorageOverview } from "@/api/client";
import ReadmeViewer from "@/components/ReadmeViewer.vue";
import RepoSummaryCards from "@/components/RepoSummaryCards.vue";
import { useSessionStore } from "@/stores/session";
import { decodeUtf8Bytes, findReadmePath } from "@/utils/files";
import { formatDateTime, shortOid } from "@/utils/format";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const { state } = useSessionStore();

const loading = ref(false);
const error = ref("");
const filesCount = ref(0);
const commits = ref([]);
const storageOverview = ref(null);
const readmePath = ref("");
const readmeContent = ref("");

async function loadOverview() {
  loading.value = true;
  error.value = "";
  try {
    const values = await Promise.all([
      getRepoFiles(props.revision),
      getCommits(props.revision, false),
      getStorageOverview()
    ]);
    const files = values[0];
    filesCount.value = files.length;
    commits.value = values[1].slice(0, 8);
    storageOverview.value = values[2];
    readmePath.value = findReadmePath(files);
    readmeContent.value = "";
    if (readmePath.value) {
      const bytes = await getBlobBytes(props.revision, readmePath.value);
      readmeContent.value = decodeUtf8Bytes(new Uint8Array(bytes));
    }
  } catch (loadOverviewError) {
    error.value = loadOverviewError.message || "Unable to load overview data.";
  } finally {
    loading.value = false;
  }
}

watch(
  function watchRevision() {
    return props.revision;
  },
  function reload() {
    loadOverview();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="overview-view">
    <repo-summary-cards
      :refs="state.refs"
      :files-count="filesCount"
      :commits-count="commits.length"
      :storage-overview="storageOverview"
    />

    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />

    <div class="content-grid">
      <el-card class="surface" body-style="padding: 22px;" data-testid="overview-readme-card">
        <div class="surface__header">
          <div>
            <h2 class="surface__title">README</h2>
            <p class="surface__subtitle">
              Primary repository landing content for revision <strong>{{ props.revision }}</strong>.
            </p>
          </div>
          <span v-if="readmePath" class="path-pill">{{ readmePath }}</span>
        </div>
        <readme-viewer
          :path="readmePath"
          :content="readmeContent"
          :loading="loading"
          empty-title="README not found"
          empty-description="This revision does not expose a top-level README.* file."
        />
      </el-card>

      <div class="stack">
        <el-card class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Repository Snapshot</h3>
              <p class="surface__subtitle">Current revision metadata from the server API.</p>
            </div>
          </div>
          <div class="kv-list">
            <div class="kv-row">
              <span>Selected revision</span>
              <strong>{{ props.revision }}</strong>
            </div>
            <div class="kv-row">
              <span>Default branch</span>
              <strong>{{ state.repo?.default_branch || state.service?.repo?.default_branch }}</strong>
            </div>
            <div class="kv-row">
              <span>Resolved head</span>
              <strong class="mono">{{ shortOid(state.repo?.head) }}</strong>
            </div>
            <div class="kv-row">
              <span>Repository path</span>
              <strong>{{ state.service?.repo?.path }}</strong>
            </div>
          </div>
        </el-card>

        <el-card class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Recent Commits</h3>
              <p class="surface__subtitle">Latest visible history entries for this revision.</p>
            </div>
          </div>
          <el-skeleton v-if="loading" :rows="5" animated />
          <el-empty
            v-else-if="!commits.length"
            description="No commits available."
          />
          <div v-else class="stack">
            <div
              v-for="commit in commits.slice(0, 6)"
              :key="commit.commit_id"
              class="timeline-card"
            >
              <div class="timeline-card__title">
                <strong>{{ commit.title }}</strong>
                <span class="mono muted">{{ shortOid(commit.commit_id) }}</span>
              </div>
              <div class="muted">{{ formatDateTime(commit.created_at) }}</div>
            </div>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>
