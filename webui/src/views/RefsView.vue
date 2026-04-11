<script setup>
import { useRouter } from "vue-router";

import RefsPanel from "@/components/RefsPanel.vue";
import { useSessionStore } from "@/stores/session";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const router = useRouter();
const { state } = useSessionStore();

function handleSelect(revision) {
  router.push({
    name: "refs",
    query: {
      revision: revision
    }
  });
}
</script>

<template>
  <div class="repo-grid" data-testid="refs-view">
    <el-card class="surface" body-style="padding: 18px;">
      <div class="surface__header">
        <div>
          <h2 class="surface__title">Refs</h2>
          <p class="surface__subtitle">
            Browse visible branches and tags, then switch the whole UI to that revision.
          </p>
        </div>
        <el-tag type="primary" effect="plain">
          Current: {{ props.revision }}
        </el-tag>
      </div>
      <refs-panel
        :refs="state.refs || { branches: [], tags: [] }"
        :current-revision="props.revision"
        @select="handleSelect"
      />
    </el-card>
  </div>
</template>
