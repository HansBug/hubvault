<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Upload } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { deleteRepoFile, deleteRepoFolder, getPathsInfo, getRepoTree } from "@/api/client";
import FileTable from "@/components/FileTable.vue";
import PathBreadcrumb from "@/components/PathBreadcrumb.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";
import { buildBreadcrumbs } from "@/utils/files";

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
const error = ref("");
const entries = ref<any[]>([]);
const directoryPath = ref("");

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

const canWrite = computed(function resolveCanWrite() {
  return Boolean(state.auth && state.auth.can_write);
});

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
      } else {
        treePath = requestedPath;
      }
    }

    directoryPath.value = treePath;
    entries.value = await getRepoTree(props.revision, treePath);
  } catch (loadFilesError) {
    error.value = loadFilesError.message || "Unable to load repository files.";
    entries.value = [];
  } finally {
    loading.value = false;
  }
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

function openUploadWorkspace() {
  router.push({
    name: "upload",
    query: {
      revision: props.revision,
      path: directoryPath.value || undefined
    }
  });
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
            Browse one directory at a time, jump across path levels, and open dedicated file or commit detail pages.
          </p>
        </div>
        <div class="app-shell__meta" v-if="canWrite">
          <el-button data-testid="files-upload-button" :icon="Upload" type="primary" plain @click="openUploadWorkspace">
            Upload
          </el-button>
        </div>
      </div>

      <path-breadcrumb :items="breadcrumbItems" />

      <el-skeleton v-if="loading" :rows="8" animated />
      <file-table
        v-else
        :entries="entries"
        :revision="props.revision"
        :can-write="canWrite"
        @open-folder="updateRoutePath"
        @open-file="openFilePath"
        @open-commit="openCommit"
        @delete-entry="handleDeleteEntry"
      />
    </el-card>
  </div>
</template>
