<script setup lang="ts">
import { House } from "@element-plus/icons-vue";
import type { PropType } from "vue";
import type { RouteLocationRaw } from "vue-router";
import { useRouter } from "vue-router";

interface BreadcrumbItem {
  ariaLabel?: string;
  current?: boolean;
  home?: boolean;
  label?: string;
  to?: RouteLocationRaw | null;
}

const props = defineProps({
  items: {
    type: Array as PropType<BreadcrumbItem[]>,
    default: function defaultItems() {
      return [];
    }
  }
});

const router = useRouter();

function navigate(item: BreadcrumbItem) {
  if (!item || !item.to) {
    return;
  }
  router.push(item.to);
}

function resolveLabel(item: BreadcrumbItem) {
  return item.label || "";
}

function isIconOnly(item: BreadcrumbItem) {
  return Boolean(item.home && !resolveLabel(item));
}
</script>

<template>
  <nav class="path-breadcrumb" data-testid="path-breadcrumb" aria-label="Repository path">
    <template v-for="(item, index) in props.items" :key="String(item.label || item.ariaLabel || index)">
      <el-button
        link
        class="path-breadcrumb__button"
        :class="{ 'is-current': item.current, 'is-icon-only': isIconOnly(item) }"
        :aria-label="item.ariaLabel || item.label || 'Navigate path level'"
        @click="navigate(item)"
      >
        <el-icon v-if="item.home"><House /></el-icon>
        <span v-if="resolveLabel(item)">{{ resolveLabel(item) }}</span>
      </el-button>
      <span v-if="index < props.items.length - 1" class="path-breadcrumb__separator">/</span>
    </template>
  </nav>
</template>
