import { createRouter, createWebHistory } from "vue-router";

import { hasSessionToken } from "./stores/session";
import CommitsView from "./views/CommitsView.vue";
import FilesView from "./views/FilesView.vue";
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
          path: "commits",
          name: "commits",
          component: CommitsView
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

router.beforeEach(function guardRoute(to) {
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
