<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { applyCommit, deleteRepoFile, deleteRepoFolder, getBlobBytes, getPathsInfo, getRepoTree, planCommit } from "@/api/client";
import FilePreviewPanel from "@/components/FilePreviewPanel.vue";
import FileTable from "@/components/FileTable.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";
import { buildBreadcrumbs, decodeUtf8Bytes, isJsonPath, isMarkdownPath, isTextLikePath } from "@/utils/files";
import { basename, buildExactUploadManifest, joinRepoPath } from "@/utils/uploads";

const PREVIEW_LIMIT = 512 * 1024;

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
const entries = ref([]);
const directoryPath = ref("");
const selectedEntry = ref(null);
const previewContent = ref("");
const previewMode = ref("empty");
const uploadFileInput = ref<HTMLInputElement | null>(null);
const uploadFolderInput = ref<HTMLInputElement | null>(null);

const breadcrumbs = computed(function resolveBreadcrumbs() {
  return buildBreadcrumbs(directoryPath.value);
});
const canWrite = computed(function resolveCanWrite() {
  return Boolean(state.auth && state.auth.can_write);
});

function parentPath(path) {
  const parts = String(path || "").split("/");
  parts.pop();
  return parts.join("/");
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

function resetPreview() {
  selectedEntry.value = null;
  previewContent.value = "";
  previewMode.value = "empty";
}

async function loadPreview(entry) {
  selectedEntry.value = entry;
  previewContent.value = "";
  if (!entry || entry.entry_type !== "file") {
    previewMode.value = "empty";
    return;
  }
  if (entry.size > PREVIEW_LIMIT) {
    previewMode.value = "binary";
    return;
  }
  if (!isMarkdownPath(entry.path) && !isJsonPath(entry.path) && !isTextLikePath(entry.path)) {
    previewMode.value = "binary";
    return;
  }

  const bytes = await getBlobBytes(props.revision, entry.path);
  let content = decodeUtf8Bytes(new Uint8Array(bytes));
  if (isJsonPath(entry.path)) {
    try {
      content = JSON.stringify(JSON.parse(content), null, 2);
      previewMode.value = "json";
    } catch (error) {
      previewMode.value = "text";
    }
  } else {
    previewMode.value = isMarkdownPath(entry.path) ? "markdown" : "text";
  }
  previewContent.value = content;
}

async function loadFiles() {
  loading.value = true;
  error.value = "";
  try {
    const requestedPath = typeof route.query.path === "string" ? route.query.path : "";
    let treePath = "";
    let previewPath = "";
    let previewEntry = null;

    if (requestedPath) {
      const info = await getPathsInfo(props.revision, [requestedPath]);
      if (info.length) {
        if (info[0].entry_type === "folder") {
          treePath = info[0].path;
        } else {
          previewPath = info[0].path;
          treePath = parentPath(previewPath);
          previewEntry = info[0];
        }
      }
    }

    directoryPath.value = treePath;
    entries.value = await getRepoTree(props.revision, treePath);

    if (previewPath) {
      const foundEntry = entries.value.find(function matchEntry(item) {
        return item.path === previewPath;
      });
      await loadPreview(foundEntry || previewEntry);
    } else {
      resetPreview();
    }
  } catch (loadFilesError) {
    error.value = loadFilesError.message || "Unable to load repository files.";
    entries.value = [];
    resetPreview();
  } finally {
    loading.value = false;
  }
}

function handleOpenFolder(path) {
  updateRoutePath(path);
}

function handleOpenFile(path) {
  updateRoutePath(path);
}

function resetInput(element) {
  if (element) {
    element.value = "";
  }
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

async function handleUploadEntries(uploadEntries, defaultMessage) {
  if (!uploadEntries.length) {
    return;
  }

  writing.value = true;
  error.value = "";
  try {
    const prompt = await ElMessageBox.prompt("Commit message", "Upload to Repository", {
      inputValue: defaultMessage,
      confirmButtonText: "Upload",
      cancelButtonText: "Cancel"
    });
    const commitMessage = String(prompt.value || "").trim() || defaultMessage;
    const manifestPayload = await buildExactUploadManifest(uploadEntries);
    const manifest = {
      revision: props.revision,
      commit_message: commitMessage,
      operations: manifestPayload.operations
    };
    const plan = await planCommit(manifest);
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
        commit_message: commitMessage,
        operations: manifestPayload.operations,
        upload_plan: plan
      },
      uploads
    );
    await bootstrapSession(props.revision, { force: true });
    await loadFiles();
    ElMessage.success("Repository upload completed.");
  } catch (uploadError) {
    if (uploadError === "cancel" || uploadError === "close") {
      return;
    }
    error.value = buildUploadErrorMessage(uploadError);
  } finally {
    writing.value = false;
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
  await handleUploadEntries(
    files.map(function mapFile(file) {
      return {
        pathInRepo: joinRepoPath(directoryPath.value, file.name),
        file: file
      };
    }),
    directoryPath.value
      ? "Upload files to " + directoryPath.value + " with hubvault"
      : "Upload files with hubvault"
  );
}

async function handleFolderInputChange(event) {
  const input = event.target;
  const files = Array.from(input && input.files ? input.files : []);
  resetInput(input);
  await handleUploadEntries(
    files.map(function mapFile(file) {
      return {
        pathInRepo: joinRepoPath(directoryPath.value, file.webkitRelativePath || file.name),
        file: file
      };
    }),
    directoryPath.value
      ? "Upload folder to " + directoryPath.value + " with hubvault"
      : "Upload folder using hubvault"
  );
}

async function handleDeleteSelected() {
  if (!selectedEntry.value) {
    return;
  }

  const targetEntry = selectedEntry.value;
  const actionLabel = targetEntry.entry_type === "folder" ? "Delete Folder" : "Delete File";
  try {
    await ElMessageBox.confirm(
      "Delete " + targetEntry.path + " from the current revision?",
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
    if (targetEntry.entry_type === "folder") {
      await deleteRepoFolder({
        path_in_repo: targetEntry.path,
        revision: props.revision,
        commit_message: "Delete folder " + targetEntry.path + " with hubvault"
      });
      updateRoutePath(directoryPath.value);
    } else {
      await deleteRepoFile({
        path_in_repo: targetEntry.path,
        revision: props.revision,
        commit_message: "Delete " + targetEntry.path + " with hubvault"
      });
      updateRoutePath(directoryPath.value);
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

    <div class="content-grid">
      <div class="stack">
        <el-card class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h2 class="surface__title">Files</h2>
              <p class="surface__subtitle">
                Browse one directory at a time, with the newest reachable commit shown for each path.
              </p>
            </div>
            <div v-if="canWrite" class="app-shell__meta">
              <el-button :loading="writing" type="primary" plain @click="triggerFileUpload">
                Upload Files
              </el-button>
              <el-button :loading="writing" plain @click="triggerFolderUpload">
                Upload Folder
              </el-button>
              <el-button
                :loading="writing"
                plain
                type="danger"
                :disabled="!selectedEntry"
                @click="handleDeleteSelected"
              >
                Delete Selected
              </el-button>
            </div>
          </div>

          <div class="app-shell__meta" style="margin-bottom: 18px;">
            <el-button plain @click="updateRoutePath('')">Repository root</el-button>
            <el-button
              v-for="breadcrumb in breadcrumbs"
              :key="breadcrumb.path"
              plain
              @click="updateRoutePath(breadcrumb.path)"
            >
              {{ breadcrumb.label }}
            </el-button>
          </div>

          <el-skeleton v-if="loading" :rows="8" animated />
          <file-table
            v-else
            :entries="entries"
            :selected-path="selectedEntry?.path || ''"
            @open-folder="handleOpenFolder"
            @open-file="handleOpenFile"
          />
        </el-card>
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
      </div>

      <file-preview-panel
        :entry="selectedEntry"
        :content="previewContent"
        :preview-mode="previewMode"
        :loading="loading"
        :revision="props.revision"
      />
    </div>
  </div>
</template>
