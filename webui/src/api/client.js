import axios from "axios";

const http = axios.create({
  timeout: 30000
});

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

export function buildDownloadUrl(revision, pathInRepo) {
  const query = new URLSearchParams({
    revision: revision
  });
  return "/api/v1/content/download/" + pathInRepo.split("/").map(encodeURIComponent).join("/") + "?" + query.toString();
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

export function getStorageOverview() {
  return request({
    method: "get",
    url: "/api/v1/maintenance/storage-overview"
  });
}

export function runQuickVerify() {
  return request({
    method: "post",
    url: "/api/v1/maintenance/quick-verify"
  });
}

export function runFullVerify() {
  return request({
    method: "post",
    url: "/api/v1/maintenance/full-verify"
  });
}
