<script setup lang="ts">
import { computed, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRouter } from "vue-router";

import { createBranchRef, createTagRef, deleteBranchRef, deleteTagRef, mergeRevision, resetBranchRef } from "@/api/client";
import RefsPanel from "@/components/RefsPanel.vue";
import { bootstrapSession, useSessionStore } from "@/stores/session";

const props = defineProps({
  revision: {
    type: String,
    default: ""
  }
});

const router = useRouter();
const { state } = useSessionStore();
const writing = ref(false);
const writeError = ref("");
const mergeResult = ref(null);

const canWrite = computed(function resolveCanWrite() {
  return Boolean(state.auth && state.auth.can_write);
});
const currentBranch = computed(function resolveCurrentBranch() {
  const branches = (state.refs && state.refs.branches) || [];
  const match = branches.find(function findBranch(item) {
    return item.name === props.revision;
  });
  return match ? match.name : "";
});
const currentTag = computed(function resolveCurrentTag() {
  const tags = (state.refs && state.refs.tags) || [];
  const match = tags.find(function findTag(item) {
    return item.name === props.revision;
  });
  return match ? match.name : "";
});

function handleSelect(revision) {
  router.push({
    name: "refs",
    query: {
      revision: revision
    }
  });
}

async function refreshRefs(nextRevision) {
  await bootstrapSession(nextRevision || props.revision, { force: true });
}

async function handleCreateBranch() {
  try {
    const prompt = await ElMessageBox.prompt("Branch name", "Create Branch", {
      inputValue: "",
      confirmButtonText: "Create",
      cancelButtonText: "Cancel"
    });
    writing.value = true;
    writeError.value = "";
    await createBranchRef({
      branch: String(prompt.value || "").trim(),
      revision: props.revision
    });
    await refreshRefs(props.revision);
    ElMessage.success("Branch created.");
  } catch (writeActionError) {
    if (writeActionError === "cancel" || writeActionError === "close") {
      return;
    }
    writeError.value = writeActionError.message || "Unable to create the branch.";
  } finally {
    writing.value = false;
  }
}

async function handleCreateTag() {
  try {
    const prompt = await ElMessageBox.prompt("Tag name", "Create Tag", {
      inputValue: "",
      confirmButtonText: "Create",
      cancelButtonText: "Cancel"
    });
    writing.value = true;
    writeError.value = "";
    await createTagRef({
      tag: String(prompt.value || "").trim(),
      revision: props.revision
    });
    await refreshRefs(props.revision);
    ElMessage.success("Tag created.");
  } catch (writeActionError) {
    if (writeActionError === "cancel" || writeActionError === "close") {
      return;
    }
    writeError.value = writeActionError.message || "Unable to create the tag.";
  } finally {
    writing.value = false;
  }
}

async function handleDeleteCurrentRef() {
  const branchName = currentBranch.value;
  const tagName = currentTag.value;
  const label = branchName || tagName;
  if (!label) {
    return;
  }

  try {
    await ElMessageBox.confirm("Delete " + label + " from the repository refs?", "Delete Ref", {
      type: "warning",
      confirmButtonText: "Delete",
      cancelButtonText: "Cancel"
    });
    writing.value = true;
    writeError.value = "";
    if (branchName) {
      await deleteBranchRef(branchName);
    } else {
      await deleteTagRef(tagName);
    }
    const nextRevision = (state.service && state.service.repo && state.service.repo.default_branch) || "main";
    await refreshRefs(nextRevision);
    router.push({
      name: "refs",
      query: {
        revision: nextRevision
      }
    });
    ElMessage.success("Reference deleted.");
  } catch (writeActionError) {
    if (writeActionError === "cancel" || writeActionError === "close") {
      return;
    }
    writeError.value = writeActionError.message || "Unable to delete the current reference.";
  } finally {
    writing.value = false;
  }
}

async function handleMergeIntoCurrent() {
  if (!currentBranch.value) {
    return;
  }

  try {
    const prompt = await ElMessageBox.prompt("Source revision", "Merge into " + currentBranch.value, {
      inputValue: "feature",
      confirmButtonText: "Merge",
      cancelButtonText: "Cancel"
    });
    writing.value = true;
    writeError.value = "";
    mergeResult.value = await mergeRevision({
      source_revision: String(prompt.value || "").trim(),
      target_revision: currentBranch.value
    });
    await refreshRefs(currentBranch.value);
    ElMessage.success("Merge request completed.");
  } catch (writeActionError) {
    if (writeActionError === "cancel" || writeActionError === "close") {
      return;
    }
    writeError.value = writeActionError.message || "Unable to merge the source revision.";
  } finally {
    writing.value = false;
  }
}

async function handleResetCurrentBranch() {
  if (!currentBranch.value) {
    return;
  }

  try {
    const prompt = await ElMessageBox.prompt("Revision to reset to", "Reset " + currentBranch.value, {
      inputValue: "",
      confirmButtonText: "Reset",
      cancelButtonText: "Cancel"
    });
    writing.value = true;
    writeError.value = "";
    await resetBranchRef({
      ref_name: currentBranch.value,
      to_revision: String(prompt.value || "").trim()
    });
    await refreshRefs(currentBranch.value);
    ElMessage.success("Branch reset completed.");
  } catch (writeActionError) {
    if (writeActionError === "cancel" || writeActionError === "close") {
      return;
    }
    writeError.value = writeActionError.message || "Unable to reset the current branch.";
  } finally {
    writing.value = false;
  }
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
      <el-alert
        v-if="writeError"
        style="margin-bottom: 18px;"
        type="error"
        :closable="false"
        :title="writeError"
      />
      <div v-if="canWrite" class="app-shell__meta" style="margin-bottom: 18px;">
        <el-button :loading="writing" type="primary" plain @click="handleCreateBranch">
          New Branch
        </el-button>
        <el-button :loading="writing" plain @click="handleCreateTag">
          New Tag
        </el-button>
        <el-button
          :loading="writing"
          plain
          :disabled="!currentBranch"
          @click="handleMergeIntoCurrent"
        >
          Merge Into Current
        </el-button>
        <el-button
          :loading="writing"
          plain
          :disabled="!currentBranch"
          @click="handleResetCurrentBranch"
        >
          Reset Current
        </el-button>
        <el-button
          :loading="writing"
          plain
          type="danger"
          :disabled="!currentBranch && !currentTag"
          @click="handleDeleteCurrentRef"
        >
          Delete Current
        </el-button>
      </div>
      <refs-panel
        :refs="state.refs || { branches: [], tags: [] }"
        :current-revision="props.revision"
        @select="handleSelect"
      />
      <el-card
        v-if="mergeResult"
        class="surface"
        body-style="padding: 18px;"
        style="margin-top: 18px;"
      >
        <div class="surface__header">
          <div>
            <h3 class="surface__title">Latest Merge Result</h3>
            <p class="surface__subtitle">
              The most recent merge attempt executed from this page.
            </p>
          </div>
          <el-tag :type="mergeResult.status === 'conflict' ? 'danger' : 'success'" effect="plain">
            {{ mergeResult.status }}
          </el-tag>
        </div>
        <div class="kv-list">
          <div class="kv-row">
            <span>Target</span>
            <strong>{{ mergeResult.target_revision }}</strong>
          </div>
          <div class="kv-row">
            <span>Source</span>
            <strong>{{ mergeResult.source_revision }}</strong>
          </div>
          <div class="kv-row">
            <span>Conflicts</span>
            <strong>{{ mergeResult.conflicts?.length || 0 }}</strong>
          </div>
        </div>
      </el-card>
    </el-card>
  </div>
</template>
