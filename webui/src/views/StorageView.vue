<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { getStorageOverview, runFullVerify, runGc, runQuickVerify, runSquashHistory } from "@/api/client";
import StorageOverviewPanel from "@/components/StorageOverviewPanel.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const { state } = useSessionStore();

const loadingOverview = ref(false);
const loadingFullVerify = ref(false);
const loadingGc = ref(false);
const loadingSquash = ref(false);
const error = ref("");
const overview = ref(null);
const quickVerify = ref(null);
const fullVerify = ref(null);
const gcReport = ref(null);
const squashReport = ref(null);

const canWrite = computed(function resolveCanWrite() {
  return Boolean(state.auth && state.auth.can_write);
});
const currentBranch = computed(function resolveCurrentBranch() {
  const branches = (state.refs && state.refs.branches) || [];
  const match = branches.find(function findBranch(item) {
    return item.name === props.revision;
  });
  return match ? match.name : "";
});

async function loadStorage() {
  loadingOverview.value = true;
  error.value = "";
  try {
    const values = await Promise.all([getStorageOverview(), runQuickVerify()]);
    overview.value = values[0];
    quickVerify.value = values[1];
  } catch (loadStorageError) {
    error.value = loadStorageError.message || "Unable to load storage diagnostics.";
  } finally {
    loadingOverview.value = false;
  }
}

async function handleRunFullVerify() {
  loadingFullVerify.value = true;
  error.value = "";
  try {
    fullVerify.value = await runFullVerify();
  } catch (fullVerifyError) {
    error.value = fullVerifyError.message || "Unable to run full verification.";
  } finally {
    loadingFullVerify.value = false;
  }
}

async function handleRunGc(dryRun) {
  loadingGc.value = true;
  error.value = "";
  try {
    if (!dryRun) {
      await ElMessageBox.confirm(
        "Run repository GC now? This will rewrite reclaimable storage and may take some time.",
        "Run GC",
        {
          type: "warning",
          confirmButtonText: "Run GC",
          cancelButtonText: "Cancel"
        }
      );
    }
    gcReport.value = await runGc({
      dry_run: Boolean(dryRun),
      prune_cache: true
    });
    await bootstrapSession(props.revision, { force: true });
    overview.value = await getStorageOverview();
    ElMessage.success(dryRun ? "GC dry-run completed." : "GC completed.");
  } catch (gcError) {
    if (gcError === "cancel" || gcError === "close") {
      return;
    }
    error.value = gcError.message || "Unable to run repository GC.";
  } finally {
    loadingGc.value = false;
  }
}

async function handleRunSquash() {
  if (!currentBranch.value) {
    return;
  }

  try {
    const prompt = await ElMessageBox.prompt(
      "Optional replacement commit message for the new root",
      "Squash " + currentBranch.value,
      {
        inputValue: "Squash history for " + currentBranch.value,
        confirmButtonText: "Squash",
        cancelButtonText: "Cancel"
      }
    );
    loadingSquash.value = true;
    error.value = "";
    squashReport.value = await runSquashHistory({
      ref_name: currentBranch.value,
      commit_message: String(prompt.value || "").trim() || null,
      run_gc: false,
      prune_cache: false
    });
    await bootstrapSession(props.revision, { force: true });
    overview.value = await getStorageOverview();
    ElMessage.success("History squash completed.");
  } catch (squashError) {
    if (squashError === "cancel" || squashError === "close") {
      return;
    }
    error.value = squashError.message || "Unable to squash the current branch history.";
  } finally {
    loadingSquash.value = false;
  }
}

watch(
  function watchStorageRoute() {
    return true;
  },
  function refreshStorage() {
    loadStorage();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="storage-view">
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />
    <el-card class="surface" body-style="padding: 18px;">
      <div class="surface__header">
        <div>
          <h2 class="surface__title">Storage</h2>
          <p class="surface__subtitle">
            Repository-wide storage footprint, safe reclamation guidance, and verification status.
          </p>
        </div>
        <div v-if="canWrite" class="app-shell__meta">
          <el-button :loading="loadingGc" plain @click="handleRunGc(true)">
            Preview GC
          </el-button>
          <el-button :loading="loadingGc" type="primary" plain @click="handleRunGc(false)">
            Run GC
          </el-button>
          <el-button
            :loading="loadingSquash"
            plain
            :disabled="!currentBranch"
            @click="handleRunSquash"
          >
            Squash Current Branch
          </el-button>
        </div>
      </div>
      <storage-overview-panel
        :overview="overview"
        :quick-verify="quickVerify"
        :full-verify="fullVerify"
        :loading-overview="loadingOverview"
        :loading-full-verify="loadingFullVerify"
        @run-full-verify="handleRunFullVerify"
      />
      <div v-if="gcReport || squashReport" class="content-grid" style="margin-top: 18px;">
        <el-card v-if="gcReport" class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Latest GC Result</h3>
              <p class="surface__subtitle">
                Most recent garbage-collection run issued from this page.
              </p>
            </div>
            <el-tag :type="gcReport.dry_run ? 'warning' : 'success'" effect="plain">
              {{ gcReport.dry_run ? "Dry Run" : "Applied" }}
            </el-tag>
          </div>
          <div class="kv-list">
            <div class="kv-row">
              <span>Reclaimed</span>
              <strong>{{ gcReport.reclaimed_size }}</strong>
            </div>
            <div class="kv-row">
              <span>Removed files</span>
              <strong>{{ gcReport.removed_file_count }}</strong>
            </div>
          </div>
        </el-card>
        <el-card v-if="squashReport" class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Latest Squash Result</h3>
              <p class="surface__subtitle">
                Most recent branch rewrite executed from this page.
              </p>
            </div>
            <el-tag type="primary" effect="plain">
              {{ squashReport.ref_name }}
            </el-tag>
          </div>
          <div class="kv-list">
            <div class="kv-row">
              <span>Rewritten commits</span>
              <strong>{{ squashReport.rewritten_commit_count }}</strong>
            </div>
            <div class="kv-row">
              <span>Dropped ancestors</span>
              <strong>{{ squashReport.dropped_ancestor_count }}</strong>
            </div>
          </div>
        </el-card>
      </div>
    </el-card>
  </div>
</template>
