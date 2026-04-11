<script setup>
import { reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { bootstrapSession, clearSession, setSessionToken } from "@/stores/session";

const route = useRoute();
const router = useRouter();

const form = reactive({
  token: ""
});
const loading = ref(false);
const error = ref("");

async function handleLogin() {
  loading.value = true;
  error.value = "";
  setSessionToken(form.token);
  try {
    const state = await bootstrapSession("");
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "";
    if (redirect && redirect.indexOf("/repo/") === 0) {
      const separator = redirect.indexOf("?") >= 0 ? "&" : "?";
      const target = redirect.indexOf("revision=") >= 0
        ? redirect
        : redirect + separator + "revision=" + encodeURIComponent(state.repoRevision);
      await router.replace(target);
    } else {
      await router.replace({
        name: "overview",
        query: {
          revision: state.repoRevision
        }
      });
    }
  } catch (loginError) {
    clearSession();
    error.value = loginError.message || "Unable to authenticate with the provided token.";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-shell" data-testid="login-view">
    <el-card class="surface login-card" body-style="padding: 24px;">
      <div class="stack">
        <div>
          <div class="app-shell__eyebrow">hubvault frontend</div>
          <h1 class="surface__title" style="font-size: 34px; margin-top: 8px;">
            Readonly Repository UI
          </h1>
          <p class="surface__subtitle" style="margin-top: 10px;">
            Sign in with a bearer token, then browse README content, files, commits, refs, and storage details on the same
            embedded service port.
          </p>
        </div>

        <el-alert
          v-if="error"
          :closable="false"
          type="error"
          :title="error"
        />

        <el-form @submit.prevent="handleLogin">
          <el-form-item label="Token">
            <el-input
              v-model="form.token"
              clearable
              placeholder="Paste a read-only or read-write token"
              show-password
            />
          </el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            style="width: 100%;"
            @click="handleLogin"
          >
            Enter Repository
          </el-button>
        </el-form>
      </div>
    </el-card>
  </div>
</template>
