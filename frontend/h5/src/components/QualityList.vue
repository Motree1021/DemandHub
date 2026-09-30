<template>
  <div class="quality-list">
    <div class="quality-title">信息完备度 <span>{{ elements.filter(element => element.status === 'OK').length }}/{{ elements.length }} 项到位</span></div>
    <div v-for="element in elements" :key="element.key" class="quality-row">
      <span>{{ element.label || labels[element.key] || element.key }}</span>
      <van-tag :type="element.status === 'OK' ? 'success' : element.status === 'VAGUE' ? 'warning' : 'default'">{{ STATUS[element.status] }}</van-tag>
      <small v-if="element.note">{{ element.note }}</small>
    </div>
    <p v-if="!elements.length" class="hint">保存后可用 AI 检查缺口；提交时系统会按标准重新检查。</p>
  </div>
</template>
<script setup lang="ts">
import type { ElementStatus } from '@/api/demand'
withDefaults(defineProps<{ elements: ElementStatus[]; labels?: Record<string, string> }>(), { labels: () => ({}) })
const STATUS = { OK: '到位', VAGUE: '需具体说明', MISSING: '待填写', SKIP: '待后续补充' }
</script>
<style scoped>
.quality-title { font-weight: 600; font-size: 14px; margin-bottom: 12px; }.quality-title span { font-weight: 400; font-size: 12px; color: #777; margin-left: 6px; }
.quality-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 10px 0; font-size: 13px; }
.quality-row small { flex-basis: 100%; color: #777; line-height: 1.6; }.hint { font-size: 12px; color: #888; line-height: 1.6; }
</style>
