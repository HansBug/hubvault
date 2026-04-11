<script setup>
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import AppShell from "@/components/AppShell.vue";
import { bootstrapSession, clearSession, useSessionStore } from "@/stores/session";

const route = useRoute();
const router = useRouter();
const { state } = useSessionStore();

const bootstrapping = ref(false);
const loadError = ref("");

const currentRevision = computed(function buildCurrentRevision() {
  return String(
    route.query.revision ||
      state.repoRevision ||
      state.repo?.default_branch ||
      state.service?.repo?.default_branch ||
      ""
  );
});

async function ensureContext() {
  bootstrapping.value = true;
  loadError.value = "";
  try {
    await bootstrapSession(typeof route.query.revision === "string" ? route.query.revision : "");
    if (!route.query.revision && state.repoRevision) {
      await router.replace({
        name: String(route.name || "overview"),
        query: {
          ...route.query,
          revision: state.repoRevision
        }
      });
    }
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      clearSession();
      await router.replace({
        name: "login",
        query: {
          redirect: route.fullPath
        }
      });
      return;
    }
    loadError.value = error.message || "Unable to bootstrap the repository UI.";
  } finally {
    bootstrapping.value = false;
  }
}

function handleChangeRevision(value) {
  router.push({
    name: String(route.name || "overview"),
    query: {
      ...route.query,
      revision: value
    }
  });
}

function handleLogout() {
  clearSession();
  router.push({
    name: "login"
  });
}

watch(
  function watchRevision() {
    return [route.name, route.query.revision].join(":");
  },
  function refreshShell() {
    ensureContext();
  },
  {
    immediate: true
  }
);
</script>

<template>
  <app-shell
    :service="state.service"
    :auth="state.auth"
    :refs="state.refs"
    :repo="state.repo"
    :current-revision="currentRevision"
    @change-revision="handleChangeRevision"
    @logout="handleLogout"
  >
    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      :title="loadError"
    />

    <el-skeleton v-else-if="bootstrapping && !state.service" :rows="8" animated />

    <router-view v-else v-slot="{ Component }">
      <component :is="Component" :revision="currentRevision" />
    </router-view>
  </app-shell>
</template>
