<!-- 补充信息卡：ext 扩展字段展示；有标准按标准定义走，无标准用 ext 键兜底（排除服务端保留键）；全空时整卡不渲染。 -->
<template>
  <el-card v-if="rows.length">
    <template #header><span class="card-title">补充信息</span></template>
    <div v-for="row in rows" :key="row.path" class="ext-row">
      <span class="k">{{ row.label }}</span>
      <span class="v">{{ row.value }}</span>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DemandRow, StandardDef, StandardField } from '@/api'
import { RESERVED_EXT_KEYS, allFields, displayValue, fieldPath, readField } from '@/utils/demand'

const props = defineProps<{ demand: DemandRow; standard: StandardDef | null }>()

const rows = computed(() => {
  const fields: StandardField[] = props.standard
    ? allFields(props.standard).filter(f => fieldPath(f).startsWith('ext.'))
    : Object.keys(props.demand.ext || {})
        .filter(key => !RESERVED_EXT_KEYS.includes(key))
        .map(key => ({ key, label: key, path: `ext.${key}`, kind: 'text' as const }))
  return fields
    .map(f => ({ path: fieldPath(f), label: f.label, value: displayValue(readField(props.demand, f), f) }))
    .filter(r => r.value)
})
</script>

<style scoped>
.card-title { font-weight: 600; }
.ext-row { display: flex; gap: 12px; padding: 6px 0; font-size: 13px; border-bottom: 1px solid #f5f6f8; }
.ext-row:last-child { border-bottom: none; }
.k { flex: none; width: 140px; color: #888; }
.v { flex: 1; color: #333; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
</style>
