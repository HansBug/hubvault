<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Back, Download, FolderOpened, Picture, View } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { buildBlobUrl, buildDownloadUrl, getBlobBytes, getPathsInfo } from "@/api/client";
import CodeViewer from "@/components/CodeViewer.vue";
import ReadmeViewer from "@/components/ReadmeViewer.vue";
import { decodeUtf8Bytes, isImagePath, isJsonPath, isMarkdownPath, isTextLikePath } from "@/utils/files";
import { formatBytes, formatDateTime, shortOid } from "@/utils/format";

const PREVIEW_LIMIT = 1024 * 1024;

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
const entry = ref<any>(null);
const fileContent = ref("");
const previewMode = ref("empty");
const markdownTab = ref("rendered");

const pathInRepo = computed(function resolvePathInRepo() {
  const value = route.params.pathMatch;
  if (Array.isArray(value)) {
    return value.join("/");
  }
  return typeof value === "string" ? value : "";
});

const directoryPath = computed(function resolveDirectoryPath() {
  const parts = pathInRepo.value.split("/");
  parts.pop();
  return parts.join("/");
});

const downloadUrl = computed(function resolveDownloadUrl() {
  if (!pathInRepo.value) {
    return "";
  }
  return buildDownloadUrl(props.revision, pathInRepo.value);
});

const imageUrl = computed(function resolveImageUrl() {
  if (!pathInRepo.value) {
    return "";
  }
  return buildBlobUrl(props.revision, pathInRepo.value);
});

async function loadFileDetail() {
  if (!pathInRepo.value) {
    entry.value = null;
    previewMode.value = "empty";
    fileContent.value = "";
    return;
  }

  loading.value = true;
  error.value = "";
  try {
    const results = await getPathsInfo(props.revision, [pathInRepo.value]);
    const nextEntry = Array.isArray(results) ? results[0] : null;
    if (!nextEntry || nextEntry.entry_type !== "file") {
      throw new Error("Selected path is not a file.");
    }

    entry.value = nextEntry;
    fileContent.value = "";
    markdownTab.value = "rendered";
    if (isImagePath(nextEntry.path)) {
      previewMode.value = "image";
      return;
    }
    if (!isTextLikePath(nextEntry.path) || nextEntry.size > PREVIEW_LIMIT) {
      previewMode.value = "binary";
      return;
    }

    const bytes = await getBlobBytes(props.revision, nextEntry.path);
    let content = decodeUtf8Bytes(new Uint8Array(bytes));
    if (isJsonPath(nextEntry.path)) {
      try {
        content = JSON.stringify(JSON.parse(content), null, 2);
      } catch (_error) {
        // Keep the raw content when the JSON payload cannot be reformatted.
      }
    }
    fileContent.value = content;
    previewMode.value = isMarkdownPath(nextEntry.path) ? "markdown" : "text";
  } catch (loadFileError) {
    error.value = loadFileError.message || "Unable to load file detail.";
    entry.value = null;
    fileContent.value = "";
    previewMode.value = "empty";
  } finally {
    loading.value = false;
  }
}

function backToDirectory() {
  router.push({
    name: "files",
    query: {
      revision: props.revision,
      path: directoryPath.value || undefined
    }
  });
}

watch(
  function watchFileInputs() {
    return [props.revision, pathInRepo.value].join(":");
  },
  function refreshFileDetail() {
    loadFileDetail();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <div class="repo-grid" data-testid="file-detail-view">
    <el-alert
      v-if="error"
      type="error"
      :closable="false"
      :title="error"
    />

    <el-card class="surface" body-style="padding: 22px;">
      <div class="surface__header">
        <div>
          <div class="detail-heading">
            <el-icon><View /></el-icon>
            <h2 class="surface__title">File Detail</h2>
          </div>
          <p class="surface__subtitle">
            Dedicated blob view with syntax highlighting, inline images, and direct download actions.
          </p>
        </div>
        <div class="app-shell__meta">
          <el-button :icon="Back" plain @click="backToDirectory">
            Back to Directory
          </el-button>
          <el-button
            v-if="downloadUrl"
            :icon="Download"
            plain
            tag="a"
            :href="downloadUrl"
          >
            Download
          </el-button>
        </div>
      </div>

      <el-skeleton v-if="loading" :rows="10" animated />
      <div v-else-if="entry" class="stack">
        <div class="detail-hero">
          <div class="stack">
            <h3 class="detail-hero__title mono">{{ entry.path }}</h3>
            <div class="app-shell__meta">
              <span class="path-pill">
                <el-icon><FolderOpened /></el-icon>
                {{ directoryPath || "Repository root" }}
              </span>
              <span class="path-pill">{{ formatBytes(entry.size) }}</span>
              <span class="path-pill">oid: <span class="mono">{{ shortOid(entry.oid) }}</span></span>
              <span class="path-pill">sha256: <span class="mono">{{ shortOid(entry.sha256) }}</span></span>
            </div>
          </div>

          <div class="stack detail-side-panel">
            <el-card class="surface" body-style="padding: 16px;">
              <div class="kv-list">
                <div class="kv-row">
                  <span>Last commit</span>
                  <strong>{{ entry.last_commit?.title || "Unknown" }}</strong>
                </div>
                <div class="kv-row">
                  <span>Updated</span>
                  <strong>{{ formatDateTime(entry.last_commit?.date) }}</strong>
                </div>
                <div class="kv-row">
                  <span>Blob ID</span>
                  <strong class="mono">{{ shortOid(entry.blob_id) }}</strong>
                </div>
                <div class="kv-row">
                  <span>ETag</span>
                  <strong class="mono">{{ shortOid(entry.etag) }}</strong>
                </div>
              </div>
            </el-card>
          </div>
        </div>

        <el-card v-if="previewMode === 'markdown'" class="surface" body-style="padding: 0;">
          <el-tabs v-model="markdownTab" class="detail-tabs">
            <el-tab-pane label="Rendered" name="rendered">
              <div class="detail-tabs__pane">
                <readme-viewer
                  :path="entry.path"
                  :content="fileContent"
                  :loading="false"
                />
              </div>
            </el-tab-pane>
            <el-tab-pane label="Source" name="source">
              <div class="detail-tabs__pane">
                <code-viewer
                  :path="entry.path"
                  :content="fileContent"
                />
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <code-viewer
          v-else-if="previewMode === 'text'"
          :path="entry.path"
          :content="fileContent"
        />

        <el-card v-else-if="previewMode === 'image'" class="surface" body-style="padding: 22px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Image Preview</h3>
              <p class="surface__subtitle">The current file is displayed directly from the repository blob route.</p>
            </div>
          </div>
          <div class="file-image-preview">
            <img
              :src="imageUrl"
              :alt="entry.path"
            >
          </div>
        </el-card>

        <el-empty
          v-else
          description="This binary file cannot be rendered inline. Use the download button to inspect it locally."
        >
          <template #image>
            <el-icon class="empty-icon"><Picture /></el-icon>
          </template>
        </el-empty>
      </div>
    </el-card>
  </div>
</template>
