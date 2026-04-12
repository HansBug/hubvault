import axios from "axios";

const http = axios.create({
  timeout: 30000
});

const WRITE_REQUEST_TIMEOUT = 0;
const MAINTENANCE_REQUEST_TIMEOUT = 0;

export interface UploadProgressEventPayload {
  loaded: number;
  total: number;
}

export interface ApplyCommitOptions {
  onUploadProgress?: (payload: UploadProgressEventPayload) => void;
}

function getStoredToken() {
  if (typeof window === "undefined" || !window.sessionStorage) {
    return "";
  }
  return window.sessionStorage.getItem("hubvault.webui.token") || "";
}

function buildErrorMessage(payload, fallbackMessage) {
  if (payload && payload.error && payload.error.message) {
    return String(payload.error.message);
  }
  if (payload && payload.detail) {
    return String(payload.detail);
  }
  return fallbackMessage;
}

http.interceptors.request.use(function attachToken(config) {
  const token = getStoredToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = "Bearer " + token;
  }
  return config;
});

http.interceptors.response.use(
  function onSuccess(response) {
    return response;
  },
  function onError(error) {
    if (error.response) {
      const payload = error.response.data;
      const wrapped = new Error(
        buildErrorMessage(payload, "Request failed with status " + error.response.status + ".")
      );
      wrapped.status = error.response.status;
      wrapped.payload = payload;
      throw wrapped;
    }
    if (error.request) {
      const wrapped = new Error("Unable to reach the hubvault server.");
      wrapped.status = 0;
      throw wrapped;
    }
    throw error;
  }
);

function request(config) {
  return http.request(config).then(function unwrap(response) {
    return response.data;
  });
}

function buildContentUrl(prefix, revision, pathInRepo) {
  const query = new URLSearchParams({
    revision: revision
  });
  const token = getStoredToken();
  if (token) {
    query.set("token", token);
  }
  return prefix + "/" + pathInRepo.split("/").map(encodeURIComponent).join("/") + "?" + query.toString();
}

export function getServiceMeta() {
  return request({
    method: "get",
    url: "/api/v1/meta/service"
  });
}

export function getWhoAmI() {
  return request({
    method: "get",
    url: "/api/v1/meta/whoami"
  });
}

export function getRepoInfo(revision) {
  return request({
    method: "get",
    url: "/api/v1/repo",
    params: {
      revision: revision
    }
  });
}

export function getRepoRefs() {
  return request({
    method: "get",
    url: "/api/v1/refs"
  });
}

export function getRepoFiles(revision) {
  return request({
    method: "get",
    url: "/api/v1/content/files",
    params: {
      revision: revision
    }
  });
}

export function getRepoTree(revision, pathInRepo) {
  const params = {
    revision: revision
  };
  if (pathInRepo) {
    params.path_in_repo = pathInRepo;
  }
  return request({
    method: "get",
    url: "/api/v1/content/tree",
    params: params
  });
}

export function getPathsInfo(revision, paths) {
  return request({
    method: "post",
    url: "/api/v1/content/paths-info",
    params: {
      revision: revision
    },
    data: paths
  });
}

export function getBlobBytes(revision, pathInRepo) {
  return http.request({
    method: "get",
    url: "/api/v1/content/blob/" + encodeURI(pathInRepo).replace(/#/g, "%23"),
    params: {
      revision: revision
    },
    responseType: "arraybuffer"
  }).then(function unwrap(response) {
    return response.data;
  });
}

export function buildBlobUrl(revision, pathInRepo) {
  return buildContentUrl("/api/v1/content/blob", revision, pathInRepo);
}

export function buildDownloadUrl(revision, pathInRepo) {
  return buildContentUrl("/api/v1/content/download", revision, pathInRepo);
}

export function getCommits(revision, formatted) {
  return request({
    method: "get",
    url: "/api/v1/history/commits",
    params: {
      revision: revision,
      formatted: Boolean(formatted)
    }
  });
}

export function getCommitDetail(commitId, formatted) {
  return request({
    method: "get",
    url: "/api/v1/history/commits/" + encodeURIComponent(commitId),
    params: {
      formatted: Boolean(formatted)
    }
  });
}

export function getStorageSummary() {
  return request({
    method: "get",
    url: "/api/v1/maintenance/storage-summary",
    timeout: MAINTENANCE_REQUEST_TIMEOUT
  });
}

export function getStorageOverview() {
  return request({
    method: "get",
    url: "/api/v1/maintenance/storage-overview",
    timeout: MAINTENANCE_REQUEST_TIMEOUT
  });
}

export function runQuickVerify() {
  return request({
    method: "post",
    url: "/api/v1/maintenance/quick-verify",
    timeout: MAINTENANCE_REQUEST_TIMEOUT
  });
}

export function runFullVerify() {
  return request({
    method: "post",
    url: "/api/v1/maintenance/full-verify",
    timeout: MAINTENANCE_REQUEST_TIMEOUT
  });
}

export function planCommit(manifest) {
  return request({
    method: "post",
    url: "/api/v1/write/commit-plan",
    data: manifest,
    timeout: WRITE_REQUEST_TIMEOUT
  });
}

export function applyCommit(manifest, uploads, options: ApplyCommitOptions = {}) {
  const items = Array.isArray(uploads) ? uploads : [];
  const handleUploadProgress = typeof options.onUploadProgress === "function"
    ? function handleProgress(event) {
      options.onUploadProgress({
        loaded: Number(event.loaded || 0),
        total: Number(event.total || 0)
      });
    }
    : undefined;
  if (!items.length) {
    return request({
      method: "post",
      url: "/api/v1/write/commit",
      data: manifest,
      onUploadProgress: handleUploadProgress,
      timeout: WRITE_REQUEST_TIMEOUT
    });
  }

  const formData = new FormData();
  formData.append("manifest", JSON.stringify(manifest));
  items.forEach(function appendUpload(item) {
    formData.append(String(item.fieldName), item.file, item.fileName || item.file.name || "upload.bin");
  });

  return request({
    method: "post",
    url: "/api/v1/write/commit",
    data: formData,
    onUploadProgress: handleUploadProgress,
    timeout: WRITE_REQUEST_TIMEOUT
  });
}

export function createBranchRef(payload) {
  return request({
    method: "post",
    url: "/api/v1/write/branches",
    data: payload
  });
}

export function deleteBranchRef(branch) {
  return request({
    method: "delete",
    url: "/api/v1/write/branches/" + encodeURIComponent(branch)
  });
}

export function createTagRef(payload) {
  return request({
    method: "post",
    url: "/api/v1/write/tags",
    data: payload
  });
}

export function deleteTagRef(tag) {
  return request({
    method: "delete",
    url: "/api/v1/write/tags/" + encodeURIComponent(tag)
  });
}

export function mergeRevision(payload) {
  return request({
    method: "post",
    url: "/api/v1/write/merge",
    data: payload
  });
}

export function resetBranchRef(payload) {
  return request({
    method: "post",
    url: "/api/v1/write/reset-ref",
    data: payload
  });
}

export function deleteRepoFile(payload) {
  return request({
    method: "post",
    url: "/api/v1/write/delete-file",
    data: payload
  });
}

export function deleteRepoFolder(payload) {
  return request({
    method: "post",
    url: "/api/v1/write/delete-folder",
    data: payload
  });
}

export function runGc(payload) {
  return request({
    method: "post",
    url: "/api/v1/maintenance/gc",
    data: payload || {},
    timeout: MAINTENANCE_REQUEST_TIMEOUT
  });
}

export function runSquashHistory(payload) {
  return request({
    method: "post",
    url: "/api/v1/maintenance/squash-history",
    data: payload,
    timeout: MAINTENANCE_REQUEST_TIMEOUT
  });
}
