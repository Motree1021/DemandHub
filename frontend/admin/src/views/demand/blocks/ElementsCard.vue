<!-- 需求要素表单（B/C/D 三区，科技需求专属）：全量渲染 27 项评估要素 + 状态胶囊 + 缺失计数；
     判型置灰（向下兼容：用户需求 B 灰、功能需求 B/C 灰）；D9 建议方案恒灰（选填·不参与评估）；
     双击行内编辑（终态禁改），保存走 PATCH /demand/{id}/elements（乐观锁 + 质量重算）。 -->
<template>
  <el-card v-if="standard">
    <template #header>
      <div class="head">
        <span class="card-title">需求要素{{ recogLabel ? `（${recogLabel}）` : '' }}</span>
        <span v-if="quality.length" class="count" :class="{ bad: missingCount > 0 }">{{ missingCount }} 项缺失</span>
        <span v-else class="count dim">提交后生成质量评估</span>
      </div>
    </template>

    <div v-for="group in zoneGroups" :key="group.zone" class="zone" :class="{ gray: group.grayed }">
      <div class="zone-title">
        {{ group.title }}
        <span class="zone-count">缺 {{ group.missingCount }}</span>
        <el-tag v-if="group.grayed" size="small" type="info" effect="plain">不参与本层级评估</el-tag>
      </div>

      <div v-for="row in group.rows" :key="row.path" class="zone-row"
           :class="{ gray: row.optional, editing: editingPath === row.path, editable: editable && editingPath !== row.path }"
           :title="editable && editingPath !== row.path ? '双击编辑' : undefined"
           @dblclick="startEdit(row)">
        <span class="k">{{ row.label }}</span>

        <!-- 行内编辑器（双击进入） -->
        <template v-if="editingPath === row.path">
          <el-select v-if="row.kind === 'enum'" v-model="editValue" size="small" class="editor" clearable>
            <el-option v-for="(label, value) in row.options" :key="value" :label="label" :value="value" />
          </el-select>
          <el-date-picker v-else-if="row.kind === 'date'" v-model="editValue" size="small" class="editor"
                          type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
          <el-input v-else v-model="editValue" size="small" class="editor" type="textarea"
                    :autosize="{ minRows: 2, maxRows: 8 }" />
          <span class="edit-ops">
            <el-button size="small" type="primary" :loading="saving" @click="saveEdit(row)">保存</el-button>
            <el-button size="small" :disabled="saving" @click="editingPath = ''">取消</el-button>
          </span>
        </template>

        <template v-else>
          <span class="v" :class="{ empty: !row.value }">{{ row.value || '未填写' }}</span>
          <el-tag v-if="row.optional" size="small" type="info" effect="plain" class="st">选填·不参与评估</el-tag>
          <el-tag v-else-if="row.status" size="small" effect="plain" class="st"
                  :type="tagType(row.status)" :title="row.note || undefined">
            {{ statusText(row.status) }}
          </el-tag>
        </template>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { demandApi } from '@/api'
import type { DemandRow, ElementStatus, StandardDef, StandardField } from '@/api'
import { ApiError } from '@/api/request'
import {
  RECOGNITION_LABELS, ZONE_TITLES, displayValue, fieldPath, grayZones, readField, recognitionLevel,
} from '@/utils/demand'

const props = defineProps<{ demand: DemandRow; standard: StandardDef; quality: ElementStatus[] }>()
const emit = defineEmits<{ updated: [payload: { demand: DemandRow; quality: ElementStatus[] }] }>()

// D9 建议方案：提报人设想仅供受理方参考（2026-10-13 拍板 assessed:false），恒灰且不参与计数；
// BA 视角标签改称「提报人建议方案」（yaml 原标签面向提报人，管理端不沿用）
const OPTIONAL_KEYS = new Set(['proposedSolution'])
const LABEL_OVERRIDES: Record<string, string> = { proposedSolution: '提报人建议方案' }

const qualityMap = computed(() => new Map(props.quality.map(q => [q.key, q])))
// 缺失口径：非到位即缺失（MISSING + VAGUE + SKIP）
const missingCount = computed(() => props.quality.filter(q => q.status !== 'OK').length)
const recogLabel = computed(() => {
  const level = recognitionLevel(props.demand.ext?.typeRecognition)
  return level ? RECOGNITION_LABELS[level] : ''
})

const gray = computed(() => grayZones(props.demand.ext?.typeRecognition))
// D 区永不置灰（向下兼容只灰 B/C），此处断言仅为通过 Set<'B'|'C'> 的类型收窄
const isGrayZone = (zone: 'B' | 'C' | 'D') => gray.value.has(zone as 'B' | 'C')

// ---- 双击行内编辑：终态 DONE/CLOSED 禁改（服务端同口径拦截）----
const editable = computed(() => !['DONE', 'CLOSED'].includes(props.demand.status))
const editingPath = ref('')
const editValue = ref<unknown>('')
const saving = ref(false)

interface ZoneRow {
  path: string; zone: string; key: string; label: string; value: string; raw: unknown
  kind: StandardField['kind']; options?: Record<string, string>
  status?: ElementStatus['status']; note?: string; optional: boolean
}

const zoneGroups = computed(() => {
  const fields = props.standard.elements.filter(f => fieldPath(f).startsWith('elements.'))
  return (['B', 'C', 'D'] as const).map(zone => {
    const rows: ZoneRow[] = fields.filter(f => f.zone === zone).map(f => {
      const q = qualityMap.value.get(f.key)
      const optional = OPTIONAL_KEYS.has(f.key)
      const raw = readField(props.demand, f)
      return {
        path: fieldPath(f), zone, key: f.key,
        label: LABEL_OVERRIDES[f.key] || f.label,
        value: displayValue(raw, f), raw,
        kind: f.kind, options: f.options,
        status: optional ? undefined : q?.status, note: q?.note,
        optional,
      }
    })
    return {
      zone,
      title: ZONE_TITLES[zone],
      rows,
      missingCount: rows.filter(r => !r.optional && r.status !== 'OK').length,
      grayed: isGrayZone(zone),
    }
  })
})

function startEdit(row: ZoneRow) {
  if (!editable.value || editingPath.value) return
  editingPath.value = row.path
  editValue.value = row.raw ?? ''
}

async function saveEdit(row: ZoneRow) {
  const value = typeof editValue.value === 'string' ? editValue.value.trim() : editValue.value
  saving.value = true
  try {
    const payload = await demandApi.updateElements(props.demand.id, {
      expectedRevision: props.demand.revision,
      elements: { [row.zone]: { [row.key]: value === '' ? null : value } },
    })
    editingPath.value = ''
    emit('updated', payload)
    ElMessage.success('已保存')
  } catch (err) {
    ElMessage.error(err instanceof ApiError ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function tagType(s: ElementStatus['status']): 'success' | 'warning' | 'info' {
  if (s === 'OK') return 'success'
  if (s === 'VAGUE') return 'warning'
  return 'info'
}
function statusText(s: ElementStatus['status']): string {
  return s === 'OK' ? '到位' : s === 'VAGUE' ? '模糊' : s === 'SKIP' ? '跳过' : '缺失'
}
</script>

<style scoped>
.card-title { font-weight: 600; }
.head { display: flex; align-items: center; justify-content: space-between; }
.count { font-size: 13px; color: #909399; font-weight: 600; }
.count.bad { color: #b45309; }
.count.dim { font-weight: 400; }
.zone { margin-bottom: 16px; }
.zone:last-child { margin-bottom: 0; }
.zone.gray { opacity: 0.45; }
.zone-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: #333; margin-bottom: 8px; padding-left: 8px; border-left: 3px solid #1f3a8a; }
.zone-count { font-size: 12px; color: #909399; font-weight: 400; }
.zone-row { display: flex; gap: 12px; align-items: baseline; padding: 6px 0 6px 11px; font-size: 13px; border-bottom: 1px solid #f5f6f8; }
.zone-row:last-child { border-bottom: none; }
.zone-row.gray { opacity: 0.6; }
.zone-row.editable { cursor: pointer; }
.zone-row.editable:hover { background: #f8fafc; }
.zone-row.editing { flex-direction: column; align-items: stretch; gap: 8px; background: #f8fafc; border-radius: 6px; padding: 8px 12px; }
.k { flex: none; width: 140px; color: #888; }
.v { flex: 1; color: #333; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
.v.empty { color: #c0c4cc; }
.st { flex: none; align-self: center; }
.editor { width: 100%; }
.edit-ops { display: flex; gap: 8px; justify-content: flex-end; }
</style>
