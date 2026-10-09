<template>
  <article class="demand-card" :class="`st-${(demand.status || '').toLowerCase()}`" tabindex="0" role="button" :aria-label="demand.title || '未命名草稿'" @click="emit('open', demand.id)" @keydown.enter="emit('open', demand.id)">
    <span class="status-icon" aria-hidden="true"><van-icon :name="statusIcon" /></span>
    <div class="card-body">
      <div class="badges">
        <span class="badge status">{{ statusLabel(demand.status) }}</span>
        <span class="badge type">{{ typeLabel(demand.demandTypeCode) }}</span>
        <span v-if="demand.urgency === 'URGENT' || demand.urgency === 'CRITICAL'" class="badge urgent">{{ urgencyLabel(demand.urgency) }}</span>
      </div>
      <h3>{{ demand.title || '未命名草稿' }}</h3>
      <p v-if="demand.content" class="preview">{{ demand.content }}</p>
      <div class="card-meta">
        <span class="meta-left"><i class="dot" aria-hidden="true" />{{ demand.demandNo || `草稿 #${demand.id}` }}<template v-if="showSubmitter"> · {{ demand.submitterName || '未提交' }}{{ demand.submitterDept ? ` ${demand.submitterDept}` : '' }}</template></span>
        <span class="meta-time">{{ fmtTime(demand.submittedAt || demand.updatedAt) }}</span>
      </div>
      <div v-if="continuable && demand.status === 'DRAFT'" class="ops">
        <button class="continue" type="button" @click.stop="emit('continue', demand.id)">继续提报 ›</button>
        <button class="close-btn" type="button" @click.stop="emit('close', demand.id)">撤销</button>
      </div>
    </div>
  </article>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { DemandEntity } from '@/api/demand'
import { statusLabel, typeLabel, urgencyLabel, fmtTime } from '@/utils/format'
const props = defineProps<{ demand: DemandEntity; showSubmitter?: boolean; continuable?: boolean }>()
const emit = defineEmits<{ (event: 'open', id: number): void; (event: 'continue', id: number): void; (event: 'close', id: number): void }>()
// 状态图标与配色（st-* 类）一一对应：草稿=编辑中、已提交=已通过、已撤销=已回收
const statusIcon = computed(() => ({ DRAFT: 'edit', SUBMITTED: 'passed', CLOSED: 'revoke' } as Record<string, string>)[props.demand.status || ''] || 'records')
</script>
<style scoped>
/* 状态配色：草稿=橙黄、已提交=品牌蓝、已撤销=灰；左边框/图标/徽章/圆点共用一组变量 */
/* 状态色用卡片左边框承载：边框沿圆角弧线整段上色（弧线两端延展到顶/底边），比裁切直条更立体 */
.demand-card { --accent: #9ca3af; --accent-tint: #f3f4f6; --accent-deep: #6b7280; position: relative; display: flex; gap: 10px; background: #fff; border-radius: 14px; border-left: 4px solid var(--accent); margin: 12px; padding: 14px 14px 12px 12px; cursor: pointer; box-shadow: 0 1px 4px rgba(15, 23, 42, 0.07); }
.demand-card.st-draft { --accent: #f59e0b; --accent-tint: #fef3c7; --accent-deep: #b45309; }
.demand-card.st-submitted { --accent: #1f3a8a; --accent-tint: #e0e7ff; --accent-deep: #1f3a8a; }
.demand-card.st-closed { --accent: #c0c4cc; --accent-tint: #f3f4f6; --accent-deep: #909399; }
/* 已撤销卡片整体灰色化：紧急徽章不再用红色 */
.demand-card.st-closed .badge.urgent { background: var(--accent-tint); color: var(--accent-deep); }
.status-icon { flex-shrink: 0; width: 34px; height: 34px; border-radius: 10px; background: var(--accent-tint); color: var(--accent-deep); display: flex; align-items: center; justify-content: center; font-size: 19px; margin-top: 2px; }
.card-body { flex: 1; min-width: 0; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; }
.badge { font-size: 11px; line-height: 1; padding: 4px 8px; border-radius: 6px; }
.badge.status { background: var(--accent-tint); color: var(--accent-deep); font-weight: 600; }
.badge.type { background: #f3f4f6; color: #6b7280; }
.badge.urgent { background: #fee2e2; color: #b91c1c; font-weight: 600; }
.demand-card h3 { font-size: 15px; font-weight: 600; margin: 8px 0 6px; color: #1f2937; overflow-wrap: anywhere; }
.preview { margin: 0 0 8px; color: #6b7280; font-size: 13px; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.card-meta { display: flex; justify-content: space-between; align-items: center; gap: 10px; font-size: 12px; color: #9ca3af; }
.meta-left { display: flex; align-items: center; gap: 5px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { flex-shrink: 0; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.meta-time { flex-shrink: 0; }
.ops { display: flex; gap: 8px; margin-top: 10px; }
.continue { border: 1px solid #a7b8d8; background: #fff; color: #1f3a8a; border-radius: 14px; padding: 5px 14px; font-size: 12px; }
.close-btn { border: 1px solid #e5b3b3; background: #fff; color: #dc2626; border-radius: 14px; padding: 5px 14px; font-size: 12px; }
</style>
