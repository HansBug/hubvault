<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { Picture } from "@element-plus/icons-vue";

const props = defineProps({
  oldImageUrl: {
    type: String,
    default: ""
  },
  newImageUrl: {
    type: String,
    default: ""
  },
  oldLabel: {
    type: String,
    default: "Before"
  },
  newLabel: {
    type: String,
    default: "After"
  }
});

let sliderSequence = 0;

const container = ref<HTMLElement | null>(null);
const fallbackMode = ref(false);

const hasComparison = computed(function resolveHasComparison() {
  return Boolean(props.oldImageUrl && props.newImageUrl);
});
const singleImageUrl = computed(function resolveSingleImageUrl() {
  return props.newImageUrl || props.oldImageUrl;
});
const singleImageLabel = computed(function resolveSingleImageLabel() {
  return props.newImageUrl ? props.newLabel : props.oldLabel;
});

function nextSliderId() {
  sliderSequence += 1;
  return "image-compare-viewer-" + String(sliderSequence);
}

async function renderComparison() {
  if (!hasComparison.value || !container.value || typeof window === "undefined") {
    fallbackMode.value = false;
    return;
  }

  fallbackMode.value = false;
  const juxtaposeModule = await import("juxtaposejs/build/js/juxtapose");
  await nextTick();

  container.value.innerHTML = "";
  const host = document.createElement("div");
  host.id = nextSliderId();
  host.className = "image-compare-viewer__host";
  container.value.appendChild(host);

  const juxtapose = (window as any).juxtapose || (juxtaposeModule as any).default || juxtaposeModule;
  if (!juxtapose || !juxtapose.JXSlider) {
    fallbackMode.value = true;
    return;
  }

  new juxtapose.JXSlider(
    "#" + host.id,
    [
      {
        src: props.oldImageUrl,
        label: props.oldLabel
      },
      {
        src: props.newImageUrl,
        label: props.newLabel
      }
    ],
    {
      showCredits: false,
      animate: false,
      startingPosition: "50%"
    }
  );
}

watch(
  function watchImageInputs() {
    return [props.oldImageUrl, props.newImageUrl, props.oldLabel, props.newLabel].join("\n");
  },
  function refreshComparison() {
    renderComparison();
  }
);

onMounted(function mountComparison() {
  renderComparison();
});
</script>

<template>
  <div class="image-compare-viewer" data-testid="image-compare-viewer">
    <div v-if="hasComparison && !fallbackMode" ref="container" class="image-compare-viewer__frame" />
    <div v-else class="image-compare-viewer__single">
      <div class="image-compare-viewer__label">
        <el-icon><Picture /></el-icon>
        <span>{{ singleImageLabel }}</span>
      </div>
      <img
        :src="singleImageUrl"
        alt="Repository image preview"
      >
    </div>
  </div>
</template>
