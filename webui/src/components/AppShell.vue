<script setup lang="ts">
import { computed } from "vue";
import { SwitchButton } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { shortOid } from "@/utils/format";
import RepoRevisionSwitch from "./RepoRevisionSwitch.vue";

const props = defineProps({
  service: {
    type: Object,
    default: null
  },
  auth: {
    type: Object,
    default: null
  },
  refs: {
    type: Object,
    default: null
  },
  repo: {
    type: Object,
    default: null
  },
  currentRevision: {
    type: String,
    default: ""
  }
});

const emit = defineEmits(["change-revision", "logout"]);

const route = useRoute();
const router = useRouter();

const menuItems = [
  { label: "Overview", name: "overview" },
  { label: "Files", name: "files" },
  { label: "Commits", name: "commits" },
  { label: "Refs", name: "refs" },
  { label: "Storage", name: "storage" }
];

const headLabel = computed(function buildHeadLabel() {
  const value = (props.repo && props.repo.head) || (props.service && props.service.repo && props.service.repo.head) || "";
  return value ? shortOid(value) : "empty";
});

function handleSelect(index) {
  router.push({
    name: index,
    query: {
      revision: props.currentRevision
    }
  });
}

function handleRevisionChange(value) {
  emit("change-revision", value);
}

function handleLogout() {
  emit("logout");
}
</script>

<template>
  <div class="page-shell" data-testid="app-shell">
    <div class="app-shell">
      <header class="app-shell__header">
        <div class="app-shell__hero">
          <div class="app-shell__brand">
            <div class="app-shell__eyebrow">
              <span>hubvault</span>
              <el-tag size="small" type="primary" effect="plain">
                {{ service?.mode || "frontend" }}
              </el-tag>
              <el-tag size="small" effect="plain">
                {{ auth?.access === "rw" ? "Read / Write" : "Read Only" }}
              </el-tag>
            </div>
            <h1 class="app-shell__title">Repository Overview</h1>
            <p class="app-shell__subtitle">
              Browse repository history, files, refs, README content, and storage diagnostics from one
              embedded page that stays aligned with the readonly HTTP API.
            </p>
            <div class="app-shell__meta">
              <span class="path-pill">default: {{ repo?.default_branch || service?.repo?.default_branch || "main" }}</span>
              <span class="path-pill">head: <span class="mono">{{ headLabel }}</span></span>
              <span class="path-pill">{{ service?.repo?.path || repo?.repo_path }}</span>
            </div>
          </div>

          <el-card class="surface" body-style="padding: 18px;">
            <div class="stack">
              <div>
                <div class="muted">Revision</div>
                <repo-revision-switch
                  :model-value="currentRevision"
                  :refs="refs || { branches: [], tags: [] }"
                  @update:model-value="handleRevisionChange"
                />
              </div>
              <div class="kv-list">
                <div class="kv-row">
                  <span>Branches</span>
                  <strong>{{ refs?.branches?.length || 0 }}</strong>
                </div>
                <div class="kv-row">
                  <span>Tags</span>
                  <strong>{{ refs?.tags?.length || 0 }}</strong>
                </div>
              </div>
              <el-button :icon="SwitchButton" plain @click="handleLogout">
                Logout
              </el-button>
            </div>
          </el-card>
        </div>

        <el-menu
          class="app-shell__nav"
          mode="horizontal"
          :default-active="String(route.name || 'overview')"
          @select="handleSelect"
        >
          <el-menu-item
            v-for="item in menuItems"
            :key="item.name"
            :index="item.name"
          >
            {{ item.label }}
          </el-menu-item>
        </el-menu>
      </header>

      <main class="app-shell__body">
        <slot />
      </main>
    </div>
  </div>
</template>
