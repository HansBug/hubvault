<script setup lang="ts">
import { Connection, PriceTag } from "@element-plus/icons-vue";

const props = defineProps({
  refs: {
    type: Object,
    default: function defaultRefs() {
      return {
        branches: [],
        tags: []
      };
    }
  },
  currentRevision: {
    type: String,
    default: ""
  }
});

const emit = defineEmits(["select"]);

function handleSelect(value) {
  emit("select", value);
}
</script>

<template>
  <div class="content-grid">
    <el-card class="surface" body-style="padding: 18px;">
      <div class="surface__header">
        <div>
          <h3 class="surface__title">Branches</h3>
          <p class="surface__subtitle">Switch between visible branch heads.</p>
        </div>
      </div>
      <div class="stack">
        <el-button
          v-for="branch in props.refs.branches || []"
          :key="'branch-' + branch.name"
          class="refs-select-button refs-select-button--branch"
          :icon="Connection"
          :plain="branch.name !== currentRevision"
          :type="branch.name === currentRevision ? 'primary' : 'info'"
          @click="handleSelect(branch.name)"
        >
          {{ branch.name }}
        </el-button>
      </div>
    </el-card>

    <el-card class="surface" body-style="padding: 18px;">
      <div class="surface__header">
        <div>
          <h3 class="surface__title">Tags</h3>
          <p class="surface__subtitle">Jump to released repository states.</p>
        </div>
      </div>
      <div class="stack">
        <el-button
          v-for="tag in props.refs.tags || []"
          :key="'tag-' + tag.name"
          class="refs-select-button refs-select-button--tag"
          :icon="PriceTag"
          :plain="tag.name !== currentRevision"
          :type="tag.name === currentRevision ? 'success' : 'default'"
          @click="handleSelect(tag.name)"
        >
          {{ tag.name }}
        </el-button>
      </div>
    </el-card>
  </div>
</template>
