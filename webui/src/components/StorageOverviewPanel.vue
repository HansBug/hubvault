<script setup>
import { formatBytes } from "@/utils/format";

const props = defineProps({
  overview: {
    type: Object,
    default: null
  },
  quickVerify: {
    type: Object,
    default: null
  },
  fullVerify: {
    type: Object,
    default: null
  },
  loadingOverview: {
    type: Boolean,
    default: false
  },
  loadingFullVerify: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(["run-full-verify"]);
</script>

<template>
  <div class="repo-grid">
    <div class="metric-grid">
      <el-card class="surface" body-style="padding: 18px;">
        <div class="muted">Total size</div>
        <div style="margin-top: 10px; font-size: 26px; font-weight: 700;">
          {{ overview ? formatBytes(overview.total_size) : "Pending" }}
        </div>
      </el-card>
      <el-card class="surface" body-style="padding: 18px;">
        <div class="muted">Reachable</div>
        <div style="margin-top: 10px; font-size: 26px; font-weight: 700;">
          {{ overview ? formatBytes(overview.reachable_size) : "Pending" }}
        </div>
      </el-card>
      <el-card class="surface" body-style="padding: 18px;">
        <div class="muted">GC reclaimable</div>
        <div style="margin-top: 10px; font-size: 26px; font-weight: 700;">
          {{ overview ? formatBytes(overview.reclaimable_gc_size) : "Pending" }}
        </div>
      </el-card>
      <el-card class="surface" body-style="padding: 18px;">
        <div class="muted">Cache reclaimable</div>
        <div style="margin-top: 10px; font-size: 26px; font-weight: 700;">
          {{ overview ? formatBytes(overview.reclaimable_cache_size) : "Pending" }}
        </div>
      </el-card>
    </div>

    <div class="content-grid">
      <el-card class="surface" body-style="padding: 18px;">
        <div class="surface__header">
          <div>
            <h3 class="surface__title">Storage Sections</h3>
            <p class="surface__subtitle">Per-section footprint and safe reclamation guidance.</p>
          </div>
        </div>
        <el-skeleton v-if="loadingOverview" :rows="6" animated />
        <el-table
          v-else
          :data="overview?.sections || []"
          empty-text="No storage section data available."
        >
          <el-table-column prop="name" label="Section" min-width="160" />
          <el-table-column prop="path" label="Path" min-width="140" />
          <el-table-column label="Total" width="120">
            <template #default="{ row }">{{ formatBytes(row.total_size) }}</template>
          </el-table-column>
          <el-table-column label="Reclaimable" width="130">
            <template #default="{ row }">{{ formatBytes(row.reclaimable_size) }}</template>
          </el-table-column>
          <el-table-column prop="reclaim_strategy" label="Strategy" width="140" />
        </el-table>
      </el-card>

      <div class="stack">
        <el-card class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Quick Verify</h3>
              <p class="surface__subtitle">Fast structural health signal.</p>
            </div>
          </div>
          <el-tag :type="quickVerify?.ok ? 'success' : 'danger'" effect="plain">
            {{ quickVerify?.ok ? "Healthy" : "Issues found" }}
          </el-tag>
          <div class="kv-list" style="margin-top: 14px;">
            <div class="kv-row">
              <span>Checked refs</span>
              <strong>{{ quickVerify?.checked_refs?.length || 0 }}</strong>
            </div>
            <div class="kv-row">
              <span>Warnings</span>
              <strong>{{ quickVerify?.warnings?.length || 0 }}</strong>
            </div>
            <div class="kv-row">
              <span>Errors</span>
              <strong>{{ quickVerify?.errors?.length || 0 }}</strong>
            </div>
          </div>
        </el-card>

        <el-card class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Full Verify</h3>
              <p class="surface__subtitle">Deeper graph and storage integrity check.</p>
            </div>
            <el-button
              :loading="loadingFullVerify"
              type="primary"
              plain
              @click="emit('run-full-verify')"
            >
              Run now
            </el-button>
          </div>
          <template v-if="fullVerify">
            <el-tag :type="fullVerify.ok ? 'success' : 'danger'" effect="plain">
              {{ fullVerify.ok ? "Healthy" : "Issues found" }}
            </el-tag>
            <div class="kv-list" style="margin-top: 14px;">
              <div class="kv-row">
                <span>Warnings</span>
                <strong>{{ fullVerify.warnings?.length || 0 }}</strong>
              </div>
              <div class="kv-row">
                <span>Errors</span>
                <strong>{{ fullVerify.errors?.length || 0 }}</strong>
              </div>
            </div>
          </template>
          <el-empty
            v-else
            description="Run the deeper verification pass on demand."
          />
        </el-card>

        <el-card class="surface" body-style="padding: 18px;">
          <div class="surface__header">
            <div>
              <h3 class="surface__title">Recommendations</h3>
              <p class="surface__subtitle">Operator guidance derived from current storage analysis.</p>
            </div>
          </div>
          <el-empty
            v-if="!overview || !(overview.recommendations || []).length"
            description="No storage recommendations at the moment."
          />
          <ul v-else style="margin: 0; padding-left: 18px; line-height: 1.8;">
            <li
              v-for="item in overview.recommendations"
              :key="item"
            >
              {{ item }}
            </li>
          </ul>
        </el-card>
      </div>
    </div>
  </div>
</template>
