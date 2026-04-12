import { createRouter, createWebHistory } from "vue-router";

import { hasSessionToken, setSessionToken } from "./stores/session";
import CommitDetailView from "./views/CommitDetailView.vue";
import CommitsView from "./views/CommitsView.vue";
import FileDetailView from "./views/FileDetailView.vue";
import FilesView from "./views/FilesView.vue";
import UploadView from "./views/UploadView.vue";
import LoginView from "./views/LoginView.vue";
import OverviewView from "./views/OverviewView.vue";
import RefsView from "./views/RefsView.vue";
import RepoLayout from "./views/RepoLayout.vue";
import StorageView from "./views/StorageView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/repo/overview"
    },
    {
      path: "/login",
      name: "login",
      component: LoginView
    },
    {
      path: "/repo",
      component: RepoLayout,
      meta: {
        requiresAuth: true
      },
      children: [
        {
          path: "",
          redirect: {
            name: "overview"
          }
        },
        {
          path: "overview",
          name: "overview",
          component: OverviewView
        },
        {
          path: "files",
          name: "files",
          component: FilesView
        },
        {
          path: "upload",
          name: "upload",
          component: UploadView
        },
        {
          path: "blob/:pathMatch(.*)*",
          name: "file-detail",
          component: FileDetailView
        },
        {
          path: "commits",
          name: "commits",
          component: CommitsView
        },
        {
          path: "commits/:commitId",
          name: "commit-detail",
          component: CommitDetailView
        },
        {
          path: "refs",
          name: "refs",
          component: RefsView
        },
        {
          path: "storage",
          name: "storage",
          component: StorageView
        }
      ]
    }
  ]
});

function sanitizeTokenQuery(query) {
  const nextQuery = Object.assign({}, query);
  delete nextQuery.token;
  return nextQuery;
}

router.beforeEach(function guardRoute(to) {
  const token = typeof to.query.token === "string" ? String(to.query.token).trim() : "";
  if (token) {
    setSessionToken(token);
    return {
      name: String(to.name || "overview"),
      params: to.params,
      query: sanitizeTokenQuery(to.query),
      hash: to.hash
    };
  }
  if (to.meta.requiresAuth && !hasSessionToken()) {
    return {
      name: "login",
      query: {
        redirect: to.fullPath
      }
    };
  }
  if (to.name === "login" && hasSessionToken()) {
    return {
      name: "overview"
    };
  }
  return true;
});

export default router;
