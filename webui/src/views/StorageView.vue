<script setup lang="ts">
import { ref, watch } from "vue";

import { getStorageOverview, runFullVerify, runQuickVerify } from "@/api/client";
import StorageOverviewPanel from "@/components/StorageOverviewPanel.vue";

defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const loadingOverview = ref(false);
const loadingFullVerify = ref(false);
const error = ref("");
const overview = ref(null);
const quickVerify = ref(null);
const fullVerify = ref(null);

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
      </div>
      <storage-overview-panel
        :overview="overview"
        :quick-verify="quickVerify"
        :full-verify="fullVerify"
        :loading-overview="loadingOverview"
        :loading-full-verify="loadingFullVerify"
        @run-full-verify="handleRunFullVerify"
      />
    </el-card>
  </div>
</template>
