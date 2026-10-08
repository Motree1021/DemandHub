<template>
  <article class="demand-card" tabindex="0" role="button" :aria-label="demand.title || '未命名草稿'" @click="emit('open', demand.id)" @keydown.enter="emit('open', demand.id)">
    <div class="card-top"><span>{{ demand.demandNo || `草稿 #${demand.id}` }}</span><van-tag :color="demand.status === 'SUBMITTED' ? '#1f3a8a' : '#777'" plain>{{ statusLabel(demand.status) }}</van-tag></div>
    <h3>{{ demand.title || '未命名草稿' }}</h3>
    <p v-if="demand.content" class="preview">{{ demand.content }}</p>
    <div class="card-meta"><span>{{ typeLabel(demand.demandTypeCode) }} · {{ urgencyLabel(demand.urgency) }}</span><span>{{ fmtTime(demand.submittedAt || demand.updatedAt) }}</span></div>
    <div v-if="continuable && demand.status === 'DRAFT'" class="ops">
      <button class="continue" type="button" @click.stop="emit('continue', demand.id)">继续提报 ›</button>
      <button class="close-btn" type="button" @click.stop="emit('close', demand.id)">撤销</button>
    </div>
    <p v-if="showSubmitter" class="submitter">{{ demand.submitterName || '未提交' }} {{ demand.submitterDept || '' }}</p>
  </article>
</template>
<script setup lang="ts">
import type { DemandEntity } from '@/api/demand'
import { statusLabel, typeLabel, urgencyLabel, fmtTime } from '@/utils/format'
defineProps<{ demand: DemandEntity; showSubmitter?: boolean; continuable?: boolean }>()
const emit = defineEmits<{ (event: 'open', id: number): void; (event: 'continue', id: number): void; (event: 'close', id: number): void }>()
</script>
<style scoped>
.demand-card { background: #fff; border-radius: 12px; margin: 12px; padding: 16px; cursor: pointer; }.card-top, .card-meta { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; color: #888; }.demand-card h3 { font-size: 15px; margin: 12px 0; color: #262e3d; }.preview { color: #777; font-size: 13px; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }.submitter { margin-bottom: 0; font-size: 12px; color: #888; }.ops { display: flex; gap: 8px; margin-top: 10px; }.continue { border: 1px solid #a7b8d8; background: #fff; color: #1f3a8a; border-radius: 14px; padding: 4px 12px; font-size: 12px; }.close-btn { border: 1px solid #e5b3b3; background: #fff; color: #dc2626; border-radius: 14px; padding: 4px 12px; font-size: 12px; }
</style>
