<!-- 需求概述卡：AI 每轮重写的四段式摘要（ext.overview），可收起/展开（默认展开）；
     无摘要时降级为提报人补充原话。底稿原文按 2026-10-13 口径不再在此展示。 -->
<template>
  <el-card class="flat-card">
    <el-collapse v-model="active">
      <el-collapse-item name="ov">
        <template #title><span class="card-title">需求概述</span></template>

        <template v-if="overviewRows.length">
          <div v-for="row in overviewRows" :key="row.key" class="ov-row">
            <div class="ov-label">{{ row.label }}</div>
            <p class="ov-text">{{ row.text }}</p>
          </div>
        </template>

        <template v-else>
          <template v-if="supplements.length">
            <div class="supp-title">后续对话中的补充原话</div>
            <div v-for="m in supplements" :key="m.id" class="supp-row">
              <small>{{ m.createdAt }}</small>
              <p>{{ m.content }}</p>
            </div>
          </template>
          <el-empty v-else description="暂无需求概述" :image-size="60" />
        </template>
      </el-collapse-item>
    </el-collapse>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DemandRow, MessageRow } from '@/api'
import { userSupplements } from '@/utils/demand'

const props = defineProps<{ demand: DemandRow; messages: MessageRow[] }>()

// 默认展开：BA 审查场景以读为主
const active = ref(['ov'])

// 固定四段标签（与 PRD FR-06 口径一致），有内容的段才展示
const OVERVIEW_LABELS: Record<string, string> = {
  problem: '问题/机会',
  userScene: '用户&场景',
  goal: '目标&期望效果',
  acceptance: '验收标准',
}
const overviewRows = computed(() => {
  const overview = (props.demand.ext?.overview || {}) as Record<string, unknown>
  return Object.entries(OVERVIEW_LABELS)
    .filter(([key]) => typeof overview[key] === 'string' && overview[key])
    .map(([key, label]) => ({ key, label, text: String(overview[key]) }))
})
const supplements = computed(() => userSupplements(props.demand, props.messages))
</script>

<style scoped>
.flat-card :deep(.el-card__body) { padding: 0 20px; }
.card-title { font-weight: 600; }
:deep(.el-collapse) { border-top: none; }
.ov-row { margin-bottom: 14px; }
.ov-row:last-child { margin-bottom: 4px; }
.ov-label { display: inline-block; font-size: 12px; font-weight: 600; color: #1f3a8a; background: #eef2ff; border-radius: 4px; padding: 2px 8px; margin-bottom: 4px; }
/* 总结文案用蓝色（贴合页面 #1f3a8a 主色调），与提报人原话类内容区分 */
.ov-text { margin: 0; font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-break: break-word; color: #2563eb; }
.supp-title { font-size: 13px; color: #555; margin-bottom: 4px; }
.supp-row { margin: 8px 0; }
.supp-row small { color: #999; display: block; }
.supp-row p { margin: 2px 0 0; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
</style>
