<!-- A · 公共要素卡：横向表单展示 A 区 8 项公共要素，每项带质量状态点（A4/A5 系统快照不评估无状态点）；
     无要素标准时降级为基本信息简表（轻量提报/异常数据兜底）。 -->
<template>
  <el-card>
    <template #header><span class="card-title">A · 公共要素</span></template>

    <el-row v-if="aFields.length" :gutter="16" class="a-grid">
      <el-col v-for="f in aFields" :key="fieldPath(f)"
              :xs="24" :sm="isWide(f) ? 24 : 12" :lg="isWide(f) ? 24 : 8">
        <div class="a-item">
          <div class="a-label">
            <span v-if="statusOf(f)" class="dot" :class="statusOf(f)!.toLowerCase()"
                  :title="statusTitle(f)" />
            {{ f.label }}
          </div>
          <div class="a-value" :class="{ empty: !valueOf(f), pre: f.kind === 'text' }">
            {{ valueOf(f) || '未填写' }}
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 降级：无标准快照时的基本信息简表 -->
    <el-descriptions v-else :column="3" border size="small">
      <el-descriptions-item label="标题" :span="3">{{ demand.title || '（无标题）' }}</el-descriptions-item>
      <el-descriptions-item label="类型">{{ typeLabel(demand.demandTypeCode) }}</el-descriptions-item>
      <el-descriptions-item label="提报人">{{ demand.submitterName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="提报部门">{{ demand.submitterDept || '—' }}</el-descriptions-item>
      <el-descriptions-item label="提交时间">{{ demand.submittedAt || '—' }}</el-descriptions-item>
      <el-descriptions-item label="期望交付">{{ demand.expectDeliveryAt || '—' }}</el-descriptions-item>
      <el-descriptions-item label="需求描述" :span="3">{{ demand.content || '—' }}</el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DemandRow, ElementStatus, StandardDef, StandardField } from '@/api'
import { displayValue, fieldPath, readField } from '@/utils/demand'
import { typeLabel } from '@/utils/status'

const props = defineProps<{ demand: DemandRow; standard: StandardDef | null; quality: ElementStatus[] }>()

// A 区字段按标准定义顺序渲染；A8 原始提报文本按 2026-10-13 口径不在此展示
const aFields = computed(() => (props.standard?.elements || []).filter(f => f.zone === 'A' && f.key !== 'content'))

const qualityMap = computed(() => new Map(props.quality.map(q => [q.key, q])))

// 标题较长独占一行，其余短字段三栏横排
const WIDE_KEYS = new Set(['title'])
const isWide = (f: StandardField) => WIDE_KEYS.has(f.key)

const statusOf = (f: StandardField) => qualityMap.value.get(f.key)?.status as 'OK' | 'VAGUE' | 'MISSING' | undefined
const statusTitle = (f: StandardField) => {
  const q = qualityMap.value.get(f.key)
  return q ? `${statusText(q.status)}${q.note ? '：' + q.note : ''}` : ''
}
function statusText(s: string) {
  return s === 'OK' ? '到位' : s === 'VAGUE' ? '模糊' : s === 'SKIP' ? '跳过' : '缺失'
}

const valueOf = (f: StandardField) => displayValue(readField(props.demand, f), f)
</script>

<style scoped>
.card-title { font-weight: 600; }
.a-grid { row-gap: 8px; }
/* 要素名与内容同一行：标签定宽不换行（6 字标签 + 状态点也放得下），行高压缩减少占位 */
.a-item { display: flex; align-items: baseline; gap: 10px; border: 1px solid #ebeef5; border-radius: 6px; padding: 4px 10px; height: 100%; box-sizing: border-box; }
.a-label { display: flex; align-items: center; gap: 6px; flex: none; width: 96px; white-space: nowrap; font-size: 12px; color: #909399; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.dot.ok { background: #67c23a; }
.dot.vague { background: #e6a23c; }
.dot.missing, .dot.skip { background: #c0c4cc; }
.a-value { flex: 1; min-width: 0; font-size: 13px; color: #303133; line-height: 1.6; word-break: break-word; }
.a-value.pre { white-space: pre-wrap; }
.a-value.empty { color: #c0c4cc; }
</style>
