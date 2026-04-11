<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  CircleCheck,
  Delete,
  FolderAdd,
  Upload,
  UploadFilled
} from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import {
  applyCommit,
  deleteRepoFile,
  deleteRepoFolder,
  getPathsInfo,
  getRepoTree,
  planCommit
} from "@/api/client";
import FileTable from "@/components/FileTable.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";
import { buildBreadcrumbs } from "@/utils/files";
import { formatBytes } from "@/utils/format";
import { basename, buildExactUploadManifest, joinRepoPath } from "@/utils/uploads";

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
const entries = ref<any[]>([]);
const directoryPath = ref("");
const uploadFileInput = ref<HTMLInputElement | null>(null);
const uploadFolderInput = ref<HTMLInputElement | null>(null);
const queueEntries = ref<any[]>([]);
const commitMessage = ref("");
const uploadProgress = ref(0);
const lastPlanStatistics = ref<any>(null);

let uploadQueueId = 0;

const breadcrumbs = computed(function resolveBreadcrumbs() {
  return buildBreadcrumbs(directoryPath.value);
});

const canWrite = computed(function resolveCanWrite() {
  return Boolean(state.auth && state.auth.can_write);
});

const queueBytes = computed(function resolveQueueBytes() {
  return queueEntries.value.reduce(function accumulate(total, item) {
    return total + Number(item.file.size || 0);
  }, 0);
});

function resetInput(element) {
  if (element) {
    element.value = "";
  }
}

function buildDefaultCommitMessage() {
  return directoryPath.value
    ? "Upload files to " + directoryPath.value + " with hubvault"
    : "Upload files with hubvault";
}

function updateRoutePath(path) {
  router.push({
    name: "files",
    query: {
      revision: props.revision,
      path: path || undefined
    }
  });
}

function openFilePath(path) {
  router.push({
    name: "file-detail",
    params: {
      pathMatch: path.split("/")
    },
    query: {
      revision: props.revision
    }
  });
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

function clearUploadQueue() {
  queueEntries.value = [];
  lastPlanStatistics.value = null;
  uploadProgress.value = 0;
  commitMessage.value = "";
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
    return left.pathInRepo.localeCompare(right.pathInRepo);
  });
  lastPlanStatistics.value = null;
  uploadProgress.value = 0;
  ensureCommitMessage();
}

async function loadFiles() {
  loading.value = true;
  error.value = "";
  try {
    const requestedPath = typeof route.query.path === "string" ? route.query.path : "";
    let treePath = "";

    if (requestedPath) {
      const info = await getPathsInfo(props.revision, [requestedPath]);
      if (info.length) {
        if (info[0].entry_type === "folder") {
          treePath = info[0].path;
        } else {
          openFilePath(info[0].path);
          return;
        }
      }
    }

    directoryPath.value = treePath;
    entries.value = await getRepoTree(props.revision, treePath);
    if (!commitMessage.value) {
      commitMessage.value = buildDefaultCommitMessage();
    }
  } catch (loadFilesError) {
    error.value = loadFilesError.message || "Unable to load repository files.";
    entries.value = [];
  } finally {
    loading.value = false;
  }
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
  uploadProgress.value = 0;
  if (!queueEntries.value.length) {
    commitMessage.value = "";
  }
}

async function handleDeleteEntry(entry) {
  const actionLabel = entry.entry_type === "folder" ? "Delete Folder" : "Delete File";
  try {
    await ElMessageBox.confirm(
      "Delete " + entry.path + " from the current revision?",
      actionLabel,
      {
        type: "warning",
        confirmButtonText: "Delete",
        cancelButtonText: "Cancel"
      }
    );
  } catch (dialogError) {
    if (dialogError === "cancel" || dialogError === "close") {
      return;
    }
    throw dialogError;
  }

  writing.value = true;
  error.value = "";
  try {
    if (entry.entry_type === "folder") {
      await deleteRepoFolder({
        path_in_repo: entry.path,
        revision: props.revision,
        commit_message: "Delete folder " + entry.path + " with hubvault"
      });
    } else {
      await deleteRepoFile({
        path_in_repo: entry.path,
        revision: props.revision,
        commit_message: "Delete " + entry.path + " with hubvault"
      });
    }
    await bootstrapSession(props.revision, { force: true });
    await loadFiles();
    ElMessage.success("Repository entry deleted.");
  } catch (deleteError) {
    error.value = deleteError.message || "Unable to delete the selected entry.";
  } finally {
    writing.value = false;
  }
}

async function submitUploadQueue() {
  if (!queueEntries.value.length) {
    return;
  }

  writing.value = true;
  error.value = "";
  uploadProgress.value = 0;
  try {
    const manifestPayload = await buildExactUploadManifest(
      queueEntries.value.map(function mapUploadEntry(item) {
        return {
          pathInRepo: item.pathInRepo,
          file: item.file
        };
      })
    );
    const nextCommitMessage = String(commitMessage.value || "").trim() || buildDefaultCommitMessage();
    const manifest = {
      revision: props.revision,
      commit_message: nextCommitMessage,
      operations: manifestPayload.operations
    };
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
        onUploadProgress: function handleUploadProgress(progressEvent) {
          if (progressEvent.total > 0) {
            uploadProgress.value = Math.max(
              uploadProgress.value,
              Math.round((progressEvent.loaded / progressEvent.total) * 100)
            );
          }
        }
      }
    );

    if (!uploads.length) {
      uploadProgress.value = 100;
    }
    await bootstrapSession(props.revision, { force: true });
    await loadFiles();
    clearUploadQueue();
    ElMessage.success("Repository upload completed.");
  } catch (uploadError) {
    error.value = buildUploadErrorMessage(uploadError);
  } finally {
    writing.value = false;
  }
}

watch(
  function watchInputs() {
    return [props.revision, route.query.path].join(":");
  },
  function reloadFiles() {
    loadFiles();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="files-view">
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />

    <el-card class="surface" body-style="padding: 18px;">
      <div class="surface__header">
        <div>
          <h2 class="surface__title">Files</h2>
          <p class="surface__subtitle">
            Browse one directory at a time, then open files in a dedicated detail page with downloads and inline preview.
          </p>
        </div>
        <div class="app-shell__meta">
          <el-button plain @click="updateRoutePath('')">Repository Root</el-button>
          <el-button
            v-for="breadcrumb in breadcrumbs"
            :key="breadcrumb.path"
            plain
            @click="updateRoutePath(breadcrumb.path)"
          >
            {{ breadcrumb.label }}
          </el-button>
        </div>
      </div>

      <el-skeleton v-if="loading" :rows="8" animated />
      <file-table
        v-else
        :entries="entries"
        :revision="props.revision"
        :can-write="canWrite"
        @open-folder="updateRoutePath"
        @open-file="openFilePath"
        @delete-entry="handleDeleteEntry"
      />
    </el-card>

    <el-card
      v-if="canWrite"
      class="surface"
      body-style="padding: 20px;"
      data-testid="upload-queue-panel"
    >
      <div class="surface__header">
        <div>
          <h3 class="surface__title">Upload Queue</h3>
          <p class="surface__subtitle">
            Add files or folders multiple times, review the queue, then commit the whole batch once.
          </p>
        </div>
        <div class="app-shell__meta">
          <el-button :icon="Upload" plain @click="triggerFileUpload">
            Add Files
          </el-button>
          <el-button :icon="FolderAdd" plain @click="triggerFolderUpload">
            Add Folder
          </el-button>
          <el-button :icon="Delete" plain :disabled="!queueEntries.length" @click="clearUploadQueue">
            Clear
          </el-button>
        </div>
      </div>

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

      <div class="upload-queue__summary">
        <span class="path-pill">{{ queueEntries.length }} files queued</span>
        <span class="path-pill">{{ formatBytes(queueBytes) }}</span>
        <span v-if="lastPlanStatistics" class="path-pill">
          {{ formatBytes(lastPlanStatistics.planned_upload_bytes || 0) }} planned upload
        </span>
        <span v-if="lastPlanStatistics && lastPlanStatistics.copy_file_count" class="path-pill">
          {{ lastPlanStatistics.copy_file_count }} copy fast paths
        </span>
        <span v-if="lastPlanStatistics && lastPlanStatistics.chunk_fast_upload_file_count" class="path-pill">
          {{ lastPlanStatistics.chunk_fast_upload_file_count }} chunk fast paths
        </span>
      </div>

      <div class="stack">
        <el-input
          v-model="commitMessage"
          placeholder="Commit message for the queued upload batch"
        />

        <el-progress
          v-if="writing"
          :percentage="uploadProgress"
          :stroke-width="14"
          status="success"
        />

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
              :aria-label="'Remove queued file ' + item.pathInRepo"
              @click="removeQueueEntry(item.id)"
            />
          </div>
        </div>
      </div>

      <div class="surface__header" style="margin-top: 18px; margin-bottom: 0;">
        <div class="surface__subtitle">
          The final commit is still validated against the current branch head, so stale upload plans are rejected safely.
        </div>
        <el-button
          :icon="CircleCheck"
          type="primary"
          :loading="writing"
          :disabled="!queueEntries.length"
          @click="submitUploadQueue"
        >
          Commit Queued Uploads
        </el-button>
      </div>
    </el-card>
  </div>
</template>
