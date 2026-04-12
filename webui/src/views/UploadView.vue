<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  CircleCheck,
  Delete,
  FolderAdd,
  Loading,
  Upload,
  UploadFilled,
  WarningFilled
} from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { applyCommit, getPathsInfo, planCommit } from "@/api/client";
import PathBreadcrumb from "@/components/PathBreadcrumb.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";
import { buildBreadcrumbs, naturalCompare } from "@/utils/files";
import { formatBytes } from "@/utils/format";
import { basename, buildExactUploadManifest, joinRepoPath } from "@/utils/uploads";

type UploadStage = "idle" | "preparing" | "planning" | "uploading" | "finalizing" | "refreshing" | "completed";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const route = useRoute();
const router = useRouter();
const { state } = useSessionStore();

const loading = ref(false);
const writing = ref(false);
const error = ref("");
const warning = ref("");
const directoryPath = ref("");
const uploadFileInput = ref<HTMLInputElement | null>(null);
const uploadFolderInput = ref<HTMLInputElement | null>(null);
const queueEntries = ref<any[]>([]);
const commitMessage = ref("");
const uploadProgress = ref(0);
const uploadStage = ref<UploadStage>("idle");
const uploadStatusTitle = ref("");
const uploadStatusMessage = ref("");
const uploadProcessedBytes = ref(0);
const uploadTotalBytes = ref(0);
const lastPlanStatistics = ref<any>(null);

let uploadQueueId = 0;

const canWrite = computed(function resolveCanWrite() {
  return Boolean(state.auth && state.auth.can_write);
});

const breadcrumbs = computed(function resolveBreadcrumbs() {
  return buildBreadcrumbs(directoryPath.value);
});

const breadcrumbItems = computed(function resolveBreadcrumbItems() {
  const items: any[] = [
    {
      home: true,
      label: "<home>",
      current: !breadcrumbs.value.length,
      ariaLabel: "Repository root",
      to: {
        name: "files",
        query: {
          revision: props.revision
        }
      }
    }
  ];
  breadcrumbs.value.forEach(function pushBreadcrumb(item, index) {
    items.push({
      label: item.label,
      current: index === breadcrumbs.value.length - 1,
      to: {
        name: "files",
        query: {
          revision: props.revision,
          path: item.path
        }
      }
    });
  });
  return items;
});

const queueBytes = computed(function resolveQueueBytes() {
  return queueEntries.value.reduce(function accumulate(total, item) {
    return total + Number(item.file.size || 0);
  }, 0);
});

const uploadStageLabel = computed(function resolveUploadStageLabel() {
  if (uploadStage.value === "preparing") {
    return "Preparing";
  }
  if (uploadStage.value === "planning") {
    return "Planning";
  }
  if (uploadStage.value === "uploading") {
    return "Uploading";
  }
  if (uploadStage.value === "finalizing") {
    return "Finalizing";
  }
  if (uploadStage.value === "refreshing") {
    return "Refreshing";
  }
  if (uploadStage.value === "completed") {
    return "Committed";
  }
  return "Idle";
});

const showUploadStatusPanel = computed(function resolveShowUploadStatusPanel() {
  return uploadStage.value !== "idle";
});

function normalizeProgress(value: number) {
  return Math.max(0, Math.min(100, Math.round(Number(value) || 0)));
}

function resetInput(element) {
  if (element) {
    element.value = "";
  }
}

function resetUploadStatus() {
  error.value = "";
  warning.value = "";
  uploadProgress.value = 0;
  uploadStage.value = "idle";
  uploadStatusTitle.value = "";
  uploadStatusMessage.value = "";
  uploadProcessedBytes.value = 0;
  uploadTotalBytes.value = 0;
}

function setUploadStatus(stage: UploadStage, title: string, message: string, progress?: number) {
  uploadStage.value = stage;
  uploadStatusTitle.value = title;
  uploadStatusMessage.value = message;
  if (typeof progress === "number") {
    uploadProgress.value = normalizeProgress(progress);
  }
}

function buildDefaultCommitMessage() {
  return directoryPath.value
    ? "Upload files to " + directoryPath.value + " with hubvault"
    : "Upload files with hubvault";
}

function buildUploadErrorMessage(uploadError) {
  const message = String((uploadError && uploadError.message) || "");
  if (
    message.indexOf("branch head changed after upload planning") >= 0 ||
    message.indexOf("re-plan the upload") >= 0 ||
    message.indexOf("expected head does not match current branch head") >= 0
  ) {
    return "Repository changed during upload planning. Refresh the page and retry the upload.";
  }
  return message || "Unable to upload files into the repository.";
}

function clearQueuedEntries() {
  queueEntries.value = [];
  lastPlanStatistics.value = null;
  commitMessage.value = "";
}

function clearUploadQueue() {
  clearQueuedEntries();
  resetUploadStatus();
}

function ensureCommitMessage() {
  if (!String(commitMessage.value || "").trim()) {
    commitMessage.value = buildDefaultCommitMessage();
  }
}

function addQueueEntries(nextEntries) {
  const table = new Map(
    queueEntries.value.map(function pairItem(item) {
      return [item.pathInRepo, item];
    })
  );

  nextEntries.forEach(function addEntry(item) {
    const existing = table.get(item.pathInRepo);
    table.set(item.pathInRepo, {
      id: existing ? existing.id : "queue-" + String(uploadQueueId++),
      pathInRepo: item.pathInRepo,
      file: item.file
    });
  });

  queueEntries.value = Array.from(table.values()).sort(function sortQueueEntries(left, right) {
    return naturalCompare(left.pathInRepo, right.pathInRepo);
  });
  lastPlanStatistics.value = null;
  resetUploadStatus();
  ensureCommitMessage();
}

async function normalizeTargetDirectory() {
  loading.value = true;
  error.value = "";
  try {
    const requestedPath = typeof route.query.path === "string" ? route.query.path.trim() : "";
    if (!requestedPath) {
      directoryPath.value = "";
      ensureCommitMessage();
      return;
    }

    const info = await getPathsInfo(props.revision, [requestedPath]);
    if (info.length) {
      if (info[0].entry_type === "folder") {
        directoryPath.value = info[0].path;
      } else {
        const parts = String(info[0].path || "").split("/");
        parts.pop();
        directoryPath.value = parts.join("/");
      }
    } else {
      directoryPath.value = requestedPath;
    }
    ensureCommitMessage();
  } catch (loadError) {
    error.value = loadError.message || "Unable to prepare the upload workspace.";
  } finally {
    loading.value = false;
  }
}

async function backToFiles() {
  await router.push({
    name: "files",
    query: {
      revision: props.revision,
      path: directoryPath.value || undefined
    }
  });
}

function triggerFileUpload() {
  if (uploadFileInput.value) {
    uploadFileInput.value.click();
  }
}

function triggerFolderUpload() {
  if (uploadFolderInput.value) {
    uploadFolderInput.value.click();
  }
}

async function handleFileInputChange(event) {
  const input = event.target;
  const files = Array.from(input && input.files ? input.files : []);
  resetInput(input);
  addQueueEntries(
    files.map(function mapFile(file) {
      return {
        pathInRepo: joinRepoPath(directoryPath.value, file.name),
        file: file
      };
    })
  );
}

async function handleFolderInputChange(event) {
  const input = event.target;
  const files = Array.from(input && input.files ? input.files : []);
  resetInput(input);
  addQueueEntries(
    files.map(function mapFile(file) {
      return {
        pathInRepo: joinRepoPath(directoryPath.value, file.webkitRelativePath || file.name),
        file: file
      };
    })
  );
}

function removeQueueEntry(id) {
  queueEntries.value = queueEntries.value.filter(function filterQueueEntry(item) {
    return item.id !== id;
  });
  lastPlanStatistics.value = null;
  resetUploadStatus();
  if (!queueEntries.value.length) {
    commitMessage.value = "";
  }
}

function updateManifestProgress(payload) {
  uploadProcessedBytes.value = Number(payload.processedBytes || 0);
  uploadTotalBytes.value = Number(payload.totalBytes || 0);
  const currentIndex = payload.totalEntries
    ? Math.min(payload.totalEntries, Math.max(payload.completedEntries + (payload.phase === "completed" ? 0 : 1), 1))
    : 0;
  const progress = uploadTotalBytes.value > 0
    ? (uploadProcessedBytes.value / uploadTotalBytes.value) * 35
    : (payload.totalEntries ? (payload.completedEntries / payload.totalEntries) * 35 : 5);
  const currentPath = payload.currentPathInRepo || "upload queue";

  if (payload.phase === "reading") {
    setUploadStatus(
      "preparing",
      "Reading queued files",
      "File " + currentIndex + " of " + payload.totalEntries + ": " + currentPath,
      progress || 5
    );
    return;
  }
  if (payload.phase === "hashing") {
    setUploadStatus(
      "preparing",
      "Hashing queued files",
      "Computing SHA-256 for " + currentPath + ".",
      Math.max(progress, 18)
    );
    return;
  }
  setUploadStatus(
    "preparing",
    "Prepared local manifest",
    "Processed " + payload.completedEntries + " of " + payload.totalEntries + " files.",
    Math.max(progress, 35)
  );
}

function updateUploadTransferProgress(progressEvent) {
  const total = Number(progressEvent.total || uploadTotalBytes.value || 0);
  const loaded = Number(progressEvent.loaded || 0);
  uploadProcessedBytes.value = loaded;
  uploadTotalBytes.value = total;

  if (total > 0 && loaded < total) {
    setUploadStatus(
      "uploading",
      "Uploading file payloads",
      "Uploaded " + formatBytes(loaded) + " of " + formatBytes(total) + ".",
      45 + (loaded / total) * 45
    );
    return;
  }
  if (total > 0) {
    setUploadStatus(
      "finalizing",
      "Finalizing commit",
      "Payload upload finished. Waiting for the server to publish the commit.",
      94
    );
  }
}

async function submitUploadQueue() {
  if (!queueEntries.value.length || writing.value) {
    return;
  }

  writing.value = true;
  error.value = "";
  warning.value = "";
  lastPlanStatistics.value = null;
  uploadProcessedBytes.value = 0;
  uploadTotalBytes.value = queueBytes.value;
  setUploadStatus(
    "preparing",
    "Preparing upload manifest",
    "Reading queued files and computing checksums.",
    1
  );

  try {
    const manifestPayload = await buildExactUploadManifest(
      queueEntries.value.map(function mapUploadEntry(item) {
        return {
          pathInRepo: item.pathInRepo,
          file: item.file
        };
      }),
      updateManifestProgress
    );
    const nextCommitMessage = String(commitMessage.value || "").trim() || buildDefaultCommitMessage();
    const manifest = {
      revision: props.revision,
      commit_message: nextCommitMessage,
      operations: manifestPayload.operations
    };

    uploadProcessedBytes.value = 0;
    uploadTotalBytes.value = 0;
    setUploadStatus(
      "planning",
      "Planning upload strategy",
      "Checking repository reuse and determining which payload bytes are still required.",
      40
    );
    const plan = await planCommit(manifest);
    lastPlanStatistics.value = plan.statistics || null;

    const uploads = (plan.operations || []).reduce(function collectUploads(accumulator, plannedOperation) {
      if (plannedOperation.type !== "add" || plannedOperation.strategy !== "upload-full") {
        return accumulator;
      }
      const uploadEntry = manifestPayload.uploads[plannedOperation.index];
      if (uploadEntry) {
        accumulator.push({
          fieldName: plannedOperation.field_name,
          file: uploadEntry.file,
          fileName: basename(uploadEntry.pathInRepo)
        });
      }
      return accumulator;
    }, []);

    uploadProcessedBytes.value = 0;
    uploadTotalBytes.value = Number((plan.statistics && plan.statistics.planned_upload_bytes) || 0);
    if (uploads.length) {
      setUploadStatus(
        "uploading",
        "Uploading file payloads",
        uploadTotalBytes.value > 0
          ? "Sending the required file payloads to the server."
          : "Streaming upload payloads to the server.",
        45
      );
    } else {
      setUploadStatus(
        "finalizing",
        "Finalizing commit",
        "No payload upload is required. Applying copy and chunk fast paths on the server.",
        88
      );
    }

    await applyCommit(
      {
        revision: props.revision,
        parent_commit: plan.base_head || null,
        commit_message: nextCommitMessage,
        operations: manifestPayload.operations,
        upload_plan: plan
      },
      uploads,
      {
        onUploadProgress: updateUploadTransferProgress
      }
    );

    setUploadStatus(
      "refreshing",
      "Refreshing repository view",
      "Reloading refs and repository metadata after the new commit.",
      98
    );

    try {
      await bootstrapSession(props.revision, { force: true });
    } catch (refreshError) {
      clearQueuedEntries();
      setUploadStatus(
        "completed",
        "Upload committed",
        "The commit was written successfully, but the repository view could not be refreshed automatically.",
        100
      );
      warning.value = (refreshError.message || "Failed to refresh the repository view.")
        + " Use Back to Files to verify the uploaded content.";
      return;
    }

    setUploadStatus(
      "completed",
      "Upload committed",
      "Repository upload completed successfully.",
      100
    );
    clearUploadQueue();
    await backToFiles();
    ElMessage.success("Repository upload completed.");
  } catch (uploadError) {
    error.value = buildUploadErrorMessage(uploadError);
    if (uploadStage.value !== "completed") {
      uploadStatusTitle.value = "Upload interrupted";
      uploadStatusMessage.value = error.value;
    }
  } finally {
    writing.value = false;
  }
}

watch(
  function watchInputs() {
    return [props.revision, route.query.path].join(":");
  },
  function refreshUploadView() {
    normalizeTargetDirectory();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="upload-view">
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />
    <el-alert
      v-if="warning"
      data-testid="upload-warning-alert"
      type="warning"
      :closable="false"
      :title="warning"
    />

    <el-card
      class="surface"
      body-style="padding: 20px;"
      data-testid="upload-queue-panel"
    >
      <div class="surface__header">
        <div>
          <div class="detail-heading">
            <el-icon><Upload /></el-icon>
            <h2 class="surface__title">Upload Files</h2>
          </div>
          <p class="surface__subtitle">
            Queue files for the current directory, append more entries in multiple rounds, then commit the batch once.
          </p>
        </div>
        <div class="app-shell__meta">
          <el-button plain :disabled="writing" @click="backToFiles">Back to Files</el-button>
          <el-button :icon="Upload" plain :disabled="!canWrite || writing" @click="triggerFileUpload">
            Add Files
          </el-button>
          <el-button :icon="FolderAdd" plain :disabled="!canWrite || writing" @click="triggerFolderUpload">
            Add Folder
          </el-button>
          <el-button :icon="Delete" plain :disabled="writing || !queueEntries.length" @click="clearUploadQueue">
            Clear
          </el-button>
        </div>
      </div>

      <path-breadcrumb :items="breadcrumbItems" />

      <input
        ref="uploadFileInput"
        data-testid="upload-file-input"
        type="file"
        multiple
        style="display: none;"
        @change="handleFileInputChange"
      >
      <input
        ref="uploadFolderInput"
        data-testid="upload-folder-input"
        type="file"
        multiple
        webkitdirectory
        style="display: none;"
        @change="handleFolderInputChange"
      >

      <el-skeleton v-if="loading" :rows="6" animated />
      <el-empty
        v-else-if="!canWrite"
        description="Upload requires a read / write token."
      >
        <template #image>
          <el-icon class="empty-icon"><UploadFilled /></el-icon>
        </template>
      </el-empty>
      <div v-else class="stack">
        <div class="upload-queue__summary">
          <span class="path-pill path-pill--compact">{{ queueEntries.length }} files queued</span>
          <span class="path-pill path-pill--compact">{{ formatBytes(queueBytes) }}</span>
          <span v-if="lastPlanStatistics" class="path-pill path-pill--compact">
            {{ formatBytes(lastPlanStatistics.planned_upload_bytes || 0) }} planned upload
          </span>
          <span v-if="lastPlanStatistics && lastPlanStatistics.copy_file_count" class="path-pill path-pill--compact">
            {{ lastPlanStatistics.copy_file_count }} copy fast paths
          </span>
          <span
            v-if="lastPlanStatistics && lastPlanStatistics.chunk_fast_upload_file_count"
            class="path-pill path-pill--compact"
          >
            {{ lastPlanStatistics.chunk_fast_upload_file_count }} chunk fast paths
          </span>
        </div>

        <el-input
          v-model="commitMessage"
          :disabled="writing"
          placeholder="Commit message for the queued upload batch"
        />

        <div
          v-if="showUploadStatusPanel"
          class="upload-status"
          data-testid="upload-status-panel"
        >
          <div class="upload-status__header">
            <div
              class="upload-status__icon"
              :class="{
                'is-active': writing,
                'is-success': uploadStage === 'completed' && !warning && !error,
                'is-warning': Boolean(warning || error)
              }"
            >
              <el-icon v-if="writing"><Loading class="is-loading" /></el-icon>
              <el-icon v-else-if="warning || error"><WarningFilled /></el-icon>
              <el-icon v-else><CircleCheck /></el-icon>
            </div>
            <div class="stack" style="gap: 4px; min-width: 0;">
              <strong data-testid="upload-status-title">{{ uploadStatusTitle }}</strong>
              <span class="muted" data-testid="upload-status-message">{{ uploadStatusMessage }}</span>
            </div>
          </div>

          <div class="upload-status__meta">
            <span class="path-pill path-pill--compact">{{ uploadStageLabel }}</span>
            <span v-if="uploadTotalBytes > 0" class="path-pill path-pill--compact">
              {{ formatBytes(uploadProcessedBytes) }} / {{ formatBytes(uploadTotalBytes) }}
            </span>
            <span
              v-else-if="uploadStage === 'finalizing' && lastPlanStatistics && !lastPlanStatistics.planned_upload_bytes"
              class="path-pill path-pill--compact"
            >
              No payload upload required
            </span>
          </div>

          <el-progress
            :percentage="uploadProgress"
            :stroke-width="12"
            :status="uploadStage === 'completed' && !warning && !error ? 'success' : undefined"
          />
        </div>

        <el-empty
          v-if="!queueEntries.length"
          description="No files are queued yet."
        >
          <template #image>
            <el-icon class="empty-icon"><UploadFilled /></el-icon>
          </template>
        </el-empty>

        <div v-else class="upload-queue__list">
          <div
            v-for="item in queueEntries"
            :key="item.id"
            class="upload-queue__item"
          >
            <div class="stack" style="gap: 6px;">
              <strong class="mono">{{ item.pathInRepo }}</strong>
              <span class="muted">{{ formatBytes(item.file.size) }}</span>
            </div>
            <el-button
              :icon="Delete"
              circle
              plain
              :disabled="writing"
              :aria-label="'Remove queued file ' + item.pathInRepo"
              @click="removeQueueEntry(item.id)"
            />
          </div>
        </div>

        <div class="surface__header upload-queue__footer">
          <div class="surface__subtitle">
            The final commit is still validated against the current branch head, so stale upload plans are rejected safely.
          </div>
          <el-button
            :icon="CircleCheck"
            type="primary"
            :loading="writing"
            :disabled="writing || !queueEntries.length"
            @click="submitUploadQueue"
          >
            Commit Queued Uploads
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>
