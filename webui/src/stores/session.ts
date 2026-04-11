import { computed, reactive, readonly } from "vue";

import { getRepoInfo, getRepoRefs, getServiceMeta, getWhoAmI } from "@/api/client";

const STORAGE_KEY = "hubvault.webui.token";

const state = reactive({
  token: "",
  auth: null,
  service: null,
  refs: null,
  repo: null,
  repoRevision: "",
  loading: false,
  error: ""
});

export function restoreSessionToken() {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return;
  }
  state.token = window.sessionStorage.getItem(STORAGE_KEY) || "";
}

export function hasSessionToken() {
  return Boolean(state.token);
}

export function setSessionToken(token) {
  state.token = String(token || "").trim();
  if (typeof window !== "undefined" && window.sessionStorage) {
    if (state.token) {
      window.sessionStorage.setItem(STORAGE_KEY, state.token);
    } else {
      window.sessionStorage.removeItem(STORAGE_KEY);
    }
  }
}

export function clearSession() {
  setSessionToken("");
  state.auth = null;
  state.service = null;
  state.refs = null;
  state.repo = null;
  state.repoRevision = "";
  state.error = "";
}

export async function bootstrapSession(revision) {
  if (!state.token) {
    throw new Error("Missing API token.");
  }

  state.loading = true;
  state.error = "";
  try {
    const baseResults = await Promise.all([
      state.service ? Promise.resolve(state.service) : getServiceMeta(),
      state.auth ? Promise.resolve(state.auth) : getWhoAmI(),
      state.refs ? Promise.resolve(state.refs) : getRepoRefs()
    ]);
    state.service = baseResults[0];
    state.auth = baseResults[1];
    state.refs = baseResults[2];

    const selectedRevision = revision || state.service.repo.default_branch || "";
    state.repo = await getRepoInfo(selectedRevision || undefined);
    state.repoRevision = selectedRevision || state.repo.default_branch || "";
    return state;
  } catch (error) {
    state.error = error.message || "Failed to load session data.";
    throw error;
  } finally {
    state.loading = false;
  }
}

export function useSessionStore() {
  return {
    state: readonly(state),
    hasToken: computed(function hasToken() {
      return Boolean(state.token);
    })
  };
}
