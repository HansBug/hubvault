<script setup lang="ts">
import { computed } from "vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: ""
  },
  refs: {
    type: Object,
    default: function defaultRefs() {
      return {
        branches: [],
        tags: []
      };
    }
  },
  disabled: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(["update:modelValue"]);

const knownValues = computed(function buildKnownValues() {
  const values = [];
  const branches = (props.refs && props.refs.branches) || [];
  const tags = (props.refs && props.refs.tags) || [];
  for (let index = 0; index < branches.length; index += 1) {
    values.push(branches[index].name);
  }
  for (let index = 0; index < tags.length; index += 1) {
    values.push(tags[index].name);
  }
  return values;
});

function handleChange(value) {
  emit("update:modelValue", value);
}
</script>

<template>
  <el-select
    :model-value="modelValue"
    :disabled="disabled"
    filterable
    class="repo-revision-switch"
    placeholder="Select branch or tag"
    @update:model-value="handleChange"
  >
    <el-option-group label="Branches">
      <el-option
        v-for="branch in refs.branches || []"
        :key="'branch-' + branch.name"
        :label="branch.name"
        :value="branch.name"
      />
    </el-option-group>
    <el-option-group label="Tags">
      <el-option
        v-for="tag in refs.tags || []"
        :key="'tag-' + tag.name"
        :label="tag.name"
        :value="tag.name"
      />
    </el-option-group>
    <el-option-group
      v-if="modelValue && knownValues.indexOf(modelValue) < 0"
      label="Selected Revision"
    >
      <el-option :label="modelValue" :value="modelValue" />
    </el-option-group>
  </el-select>
</template>
