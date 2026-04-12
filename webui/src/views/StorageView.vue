<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, Loading, WarningFilled } from "@element-plus/icons-vue";

import { getStorageOverview, getStorageSummary, runFullVerify, runGc, runQuickVerify, runSquashHistory } from "@/api/client";
import StorageOverviewPanel from "@/components/StorageOverviewPanel.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";

type StorageOperation = "" | "summary" | "overview" | "quick-verify" | "full-verify" | "gc-preview" | "gc-run" | "squash";
type StorageStatusTone = "info" | "success" | "warning";

const STORAGE_OPERATION_HINTS: Record<string, string[]> = {
  summary: [
    "Measuring repository footprint.",
    "Reading lightweight metadata.",
    "Preparing quick storage cards."
  ],
  overview: [
    "Scanning repository sections.",
    "Summarizing reclaimable storage.",
    "Preparing operator guidance."
  ],
  "quick-verify": [
    "Checking refs and reachable objects.",
    "Validating lightweight repository invariants.",
    "Assembling the quick verification summary."
  ],
  "full-verify": [
    "Walking the repository graph.",
    "Inspecting stored payload integrity.",
    "Collecting verification findings."
  ],
  "gc-preview": [
    "Estimating reclaimable payloads.",
    "Reviewing safe cleanup opportunities.",
    "Preparing the dry-run report."
  ],
  "gc-run": [
    "Rewriting reclaimable storage.",
    "Publishing cleanup results.",
    "Refreshing repository metadata."
  ],
  squash: [
    "Rebuilding the current branch root.",
    "Publishing the rewritten branch head.",
    "Refreshing repository metadata."
  ]
};

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const { state } = useSessionStore();

const activeOperation = ref<StorageOperation>("");
const statusTone = ref<StorageStatusTone>("info");
const statusTitle = ref("Storage analysis is on demand");
const statusBaseMessage = ref(
  "Large repositories can take time to inspect. Run storage analysis or verification only when needed."
);
const statusElapsedSeconds = ref(0);
const statusTick = ref(0);
const error = ref("");
const summary = ref<any>(null);
const overview = ref<any>(null);
const quickVerify = ref<any>(null);
const fullVerify = ref<any>(null);
const gcReport = ref<any>(null);
const squashReport = ref<any>(null);

let statusInterval: ReturnType<typeof setInterval> | null = null;

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
const isBusy = computed(function resolveBusyState() {
  return Boolean(activeOperation.value);
});
const loadingSummary = computed(function resolveLoadingSummary() {
  return activeOperation.value === "summary";
});
const loadingOverview = computed(function resolveLoadingOverview() {
  return activeOperation.value === "overview";
});
const loadingQuickVerify = computed(function resolveLoadingQuickVerify() {
  return activeOperation.value === "quick-verify";
});
const loadingFullVerify = computed(function resolveLoadingFullVerify() {
  return activeOperation.value === "full-verify";
});
const loadingGc = computed(function resolveLoadingGc() {
  return activeOperation.value === "gc-preview" || activeOperation.value === "gc-run";
});
const loadingSquash = computed(function resolveLoadingSquash() {
  return activeOperation.value === "squash";
});
const statusPhaseLabel = computed(function resolveStatusPhaseLabel() {
  if (activeOperation.value === "summary") {
    return "Loading summary";
  }
  if (activeOperation.value === "overview") {
    return "Loading analysis";
  }
  if (activeOperation.value === "quick-verify") {
    return "Quick verify";
  }
  if (activeOperation.value === "full-verify") {
    return "Full verify";
  }
  if (activeOperation.value === "gc-preview") {
    return "GC preview";
  }
  if (activeOperation.value === "gc-run") {
    return "GC";
  }
  if (activeOperation.value === "squash") {
    return "Squashing";
  }
  if (statusTone.value === "success") {
    return "Completed";
  }
  if (statusTone.value === "warning") {
    return "Needs attention";
  }
  return "Idle";
});
const statusMessage = computed(function resolveStatusMessage() {
  const base = String(statusBaseMessage.value || "").trim();
  if (!activeOperation.value) {
    return base;
  }
  const hints = STORAGE_OPERATION_HINTS[activeOperation.value] || [];
  const hint = hints.length ? hints[statusTick.value % hints.length] : "";
  const parts = [base];
  if (hint) {
    parts.push(hint);
  }
  parts.push("Elapsed " + formatElapsed(statusElapsedSeconds.value) + ".");
  return parts.filter(Boolean).join(" ");
});

function formatElapsed(seconds: number) {
  const total = Math.max(0, Number(seconds || 0));
  const minutes = Math.floor(total / 60);
  const remain = total % 60;
  if (minutes > 0) {
    return String(minutes) + "m " + String(remain).padStart(2, "0") + "s";
  }
  return String(remain) + "s";
}

function stopStatusTicker() {
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
}

function setIdleStatus() {
  stopStatusTicker();
  activeOperation.value = "";
  statusTone.value = "info";
  statusTitle.value = "Storage analysis is on demand";
  statusBaseMessage.value =
    "Large repositories can take time to inspect. Run storage analysis or verification only when needed.";
  statusElapsedSeconds.value = 0;
  statusTick.value = 0;
}

function startStatus(operation: StorageOperation, title: string, message: string) {
  stopStatusTicker();
  activeOperation.value = operation;
  statusTone.value = "info";
  statusTitle.value = title;
  statusBaseMessage.value = message;
  statusElapsedSeconds.value = 0;
  statusTick.value = 0;
  statusInterval = setInterval(function advanceStorageStatus() {
    statusElapsedSeconds.value += 1;
    statusTick.value += 1;
  }, 1000);
}

function updateStatus(title: string, message: string) {
  statusTitle.value = title;
  statusBaseMessage.value = message;
  statusTick.value = 0;
}

function finishStatus(title: string, message: string, tone: StorageStatusTone = "success") {
  stopStatusTicker();
  activeOperation.value = "";
  statusTone.value = tone;
  statusTitle.value = title;
  statusBaseMessage.value = message;
}

function resetReportsForRevision() {
  summary.value = null;
  overview.value = null;
  quickVerify.value = null;
  fullVerify.value = null;
  gcReport.value = null;
  squashReport.value = null;
  error.value = "";
  setIdleStatus();
}

async function runStorageTask<T>(
  operation: StorageOperation,
  startTitle: string,
  startMessage: string,
  successTitle: string,
  successMessage: string,
  task: () => Promise<T>,
  failureMessage: string
) {
  startStatus(operation, startTitle, startMessage);
  error.value = "";
  try {
    const result = await task();
    finishStatus(successTitle, successMessage, "success");
    return result;
  } catch (taskError) {
    const message = taskError instanceof Error ? taskError.message : String(taskError || "");
    error.value = message || failureMessage;
    finishStatus("Storage task interrupted", error.value, "warning");
    return null;
  }
}

async function handleLoadSummary() {
  const result = await runStorageTask(
    "summary",
    "Loading quick storage summary",
    "Measuring the current repository footprint without running the heavier storage analysis.",
    "Quick storage summary ready",
    "Loaded immediate storage metrics from the live repository state.",
    function fetchStorageSummary() {
      return getStorageSummary();
    },
    "Unable to load the quick storage summary."
  );
  if (result) {
    summary.value = result;
  }
}

async function handleLoadOverview() {
  const result = await runStorageTask(
    "overview",
    "Loading storage analysis",
    "Reading repository storage metadata and reclaimable section sizes.",
    "Storage analysis ready",
    "Loaded the current repository storage analysis.",
    function fetchStorageOverview() {
      return getStorageOverview();
    },
    "Unable to load storage diagnostics."
  );
  if (result) {
    overview.value = result;
  }
}

async function handleRunQuickVerify() {
  const result = await runStorageTask(
    "quick-verify",
    "Running quick verify",
    "Checking repository structure without loading the heavier maintenance reports.",
    "Quick verify ready",
    "Finished the lightweight verification pass.",
    function executeQuickVerify() {
      return runQuickVerify();
    },
    "Unable to run quick verification."
  );
  if (result) {
    quickVerify.value = result;
  }
}

async function handleRunFullVerify() {
  const result = await runStorageTask(
    "full-verify",
    "Running full verify",
    "Performing the deeper repository graph and payload integrity scan.",
    "Full verify ready",
    "Finished the deeper verification pass.",
    function executeFullVerify() {
      return runFullVerify();
    },
    "Unable to run full verification."
  );
  if (result) {
    fullVerify.value = result;
  }
}

async function refreshSummary(message: string) {
  updateStatus("Refreshing quick storage summary", message);
  summary.value = await getStorageSummary();
}

async function refreshOverviewIfLoaded(message: string) {
  if (overview.value === null) {
    return;
  }
  updateStatus("Refreshing storage analysis", message);
  overview.value = await getStorageOverview();
}

function clearVerificationResults() {
  quickVerify.value = null;
  fullVerify.value = null;
}

async function handleRunGc(dryRun: boolean) {
  if (!dryRun) {
    try {
      await ElMessageBox.confirm(
        "Run repository GC now? This will rewrite reclaimable storage and may take some time.",
        "Run GC",
        {
          type: "warning",
          confirmButtonText: "Run GC",
          cancelButtonText: "Cancel"
        }
      );
    } catch (confirmError) {
      if (confirmError === "cancel" || confirmError === "close") {
        return;
      }
      throw confirmError;
    }
  }

  const result = await runStorageTask(
    dryRun ? "gc-preview" : "gc-run",
    dryRun ? "Previewing reclaimable storage" : "Running garbage collection",
    dryRun
      ? "Estimating reclaimable bytes without mutating repository storage."
      : "Rewriting reclaimable storage and updating repository metadata.",
    dryRun ? "GC preview ready" : "GC completed",
    dryRun ? "Calculated the current GC dry-run report." : "Repository garbage collection finished successfully.",
    async function executeGc() {
      const report = await runGc({
        dry_run: Boolean(dryRun),
        prune_cache: true
      });
      gcReport.value = report;
      updateStatus(
        "Refreshing repository session",
        "Reloading refs and repository metadata after the GC operation."
      );
      await bootstrapSession(props.revision, { force: true });
      await refreshSummary("Refreshing the quick storage summary after the GC operation.");
      clearVerificationResults();
      await refreshOverviewIfLoaded("Refreshing the previously requested storage overview after GC.");
      return report;
    },
    "Unable to run repository GC."
  );

  if (result) {
    ElMessage.success(dryRun ? "GC dry-run completed." : "GC completed.");
  }
}

async function handleRunSquash() {
  if (!currentBranch.value) {
    return;
  }

  let prompt;
  try {
    prompt = await ElMessageBox.prompt(
      "Optional replacement commit message for the new root",
      "Squash " + currentBranch.value,
      {
        inputValue: "Squash history for " + currentBranch.value,
        confirmButtonText: "Squash",
        cancelButtonText: "Cancel"
      }
    );
  } catch (promptError) {
    if (promptError === "cancel" || promptError === "close") {
      return;
    }
    throw promptError;
  }

  const result = await runStorageTask(
    "squash",
    "Squashing current branch",
    "Rebuilding the selected branch into a compact history root.",
    "History squash completed",
    "The current branch history was rewritten successfully.",
    async function executeSquash() {
      const report = await runSquashHistory({
        ref_name: currentBranch.value,
        commit_message: String(prompt?.value || "").trim() || null,
        run_gc: false,
        prune_cache: false
      });
      squashReport.value = report;
      updateStatus(
        "Refreshing repository session",
        "Reloading refs and repository metadata after the history rewrite."
      );
      await bootstrapSession(props.revision, { force: true });
      await refreshSummary("Refreshing the quick storage summary after the history rewrite.");
      clearVerificationResults();
      await refreshOverviewIfLoaded("Refreshing the previously requested storage overview after the squash operation.");
      return report;
    },
    "Unable to squash the current branch history."
  );

  if (result) {
    ElMessage.success("History squash completed.");
  }
}

watch(
  function watchRevision() {
    return props.revision;
  },
  function resetStorageView() {
    resetReportsForRevision();
    void handleLoadSummary();
  },
  {
    immediate: true
  }
);

onBeforeUnmount(function cleanupStorageView() {
  stopStatusTicker();
});
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
          <el-button :loading="loadingGc" :disabled="isBusy" plain @click="handleRunGc(true)">
            Preview GC
          </el-button>
          <el-button :loading="loadingGc" :disabled="isBusy" type="primary" plain @click="handleRunGc(false)">
            Run GC
          </el-button>
          <el-button
            :loading="loadingSquash"
            plain
            :disabled="isBusy || !currentBranch"
            @click="handleRunSquash"
          >
            Squash Current Branch
          </el-button>
        </div>
      </div>

      <div class="storage-status" data-testid="storage-status-panel">
        <div class="storage-status__header">
          <div
            class="storage-status__icon"
            :class="{
              'is-active': isBusy,
              'is-success': !isBusy && statusTone === 'success',
              'is-warning': statusTone === 'warning'
            }"
          >
            <el-icon v-if="isBusy"><Loading class="is-loading" /></el-icon>
            <el-icon v-else-if="statusTone === 'warning'"><WarningFilled /></el-icon>
            <el-icon v-else><CircleCheck /></el-icon>
          </div>
          <div class="stack" style="gap: 4px; min-width: 0;">
            <strong data-testid="storage-status-title">{{ statusTitle }}</strong>
            <span class="muted" data-testid="storage-status-message">{{ statusMessage }}</span>
          </div>
        </div>

        <div class="storage-status__meta">
          <span class="path-pill path-pill--compact">{{ statusPhaseLabel }}</span>
          <span v-if="isBusy" class="path-pill path-pill--compact">{{ formatElapsed(statusElapsedSeconds) }} elapsed</span>
          <span v-else-if="overview" class="path-pill path-pill--compact">Overview loaded</span>
          <span v-else-if="summary" class="path-pill path-pill--compact">Quick summary ready</span>
          <span v-else class="path-pill path-pill--compact">No heavy analysis yet</span>
        </div>
      </div>

      <storage-overview-panel
        :summary="summary"
        :overview="overview"
        :quick-verify="quickVerify"
        :full-verify="fullVerify"
        :loading-summary="loadingSummary"
        :loading-overview="loadingOverview"
        :loading-quick-verify="loadingQuickVerify"
        :loading-full-verify="loadingFullVerify"
        :actions-disabled="isBusy"
        @load-overview="handleLoadOverview"
        @run-quick-verify="handleRunQuickVerify"
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
