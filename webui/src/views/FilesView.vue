<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { getBlobBytes, getPathsInfo, getRepoTree } from "@/api/client";
import FilePreviewPanel from "@/components/FilePreviewPanel.vue";
import FileTable from "@/components/FileTable.vue";
import { buildBreadcrumbs, decodeUtf8Bytes, isJsonPath, isMarkdownPath, isTextLikePath } from "@/utils/files";

const PREVIEW_LIMIT = 512 * 1024;

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
const entries = ref([]);
const directoryPath = ref("");
const selectedEntry = ref(null);
const previewContent = ref("");
const previewMode = ref("empty");

const breadcrumbs = computed(function resolveBreadcrumbs() {
  return buildBreadcrumbs(directoryPath.value);
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
