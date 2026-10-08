<template>
  <van-popup :show="show" position="bottom" round :style="{ height: '92%' }" @update:show="emit('update:show', $event)">
    <div class="full-form">
      <div class="sheet-header"><strong>完整要素表单</strong><van-icon name="cross" size="20" @click="emit('update:show', false)" /></div>
      <div class="sheet-body">
        <p class="degrade-tip">可直接填写；AI 对话整理的要素也会同步到这里。</p>
        <template v-for="group in zoneGroups" :key="group.zone">
          <div v-if="group.fields.length" class="form-card">
            <div class="zone-header"><strong>{{ group.title }}<small>（{{ group.note }}）</small></strong><van-tag v-if="group.zone === 'B' && businessConfirmed" type="danger" plain>已确认为业务需求 · 必填</van-tag></div>
            <standard-field v-for="field in group.fields" :key="fieldPath(field)" :field="field" :model-value="readField(form, field)" :disabled="locked" :class="{ 'ai-flash': flash.has(fieldPath(field)) }" @update:model-value="emit('update-field', field, $event)" />
          </div>
        </template>
        <div v-if="plainFields.length" class="form-card">
          <standard-field v-for="field in plainFields" :key="fieldPath(field)" :field="field" :model-value="readField(form, field)" :disabled="locked" :class="{ 'ai-flash': flash.has(fieldPath(field)) }" @update:model-value="emit('update-field', field, $event)" />
        </div>
        <div v-if="extraFields.length" class="form-card">
          <van-collapse v-model="expanded"><van-collapse-item title="补充信息（选填）" name="extra">
            <standard-field v-for="field in extraFields" :key="fieldPath(field)" :field="field" :model-value="readField(form, field)" :disabled="locked" :class="{ 'ai-flash': flash.has(fieldPath(field)) }" @update:model-value="emit('update-field', field, $event)" />
          </van-collapse-item></van-collapse>
        </div>
        <div class="form-card quality-card"><quality-list :elements="quality" :labels="labels" /></div>
        <div v-if="draftId" class="form-card status-card">
          <van-collapse v-model="statusExpanded"><van-collapse-item :title="`E 区 · 状态信息（版本 ${revision} · 留痕 ${changeLogs.length} 条）`" name="status">
            <div class="status-block"><h3>字段来源</h3><p v-for="row in sourceRows" :key="row.path" class="status-row"><span class="path">{{ row.label }}</span><van-tag :type="row.tagType" plain>{{ row.sourceLabel }}</van-tag></p></div>
            <div v-if="changeLogs.length" class="status-block"><h3>变更留痕</h3><p v-for="log in changeLogs" :key="log.id" class="status-row"><span class="path">{{ logLabel(log.fieldKey) }}</span><span class="diff">{{ display(log.oldValue) }} → {{ display(log.newValue) }}</span><small>{{ fmtTime(log.createdAt) }}</small></p></div>
          </van-collapse-item></van-collapse>
        </div>
      </div>
      <div class="sheet-actions">
        <van-button block plain type="primary" :loading="saving" :disabled="locked" @click="emit('save')">保存草稿</van-button>
        <van-button block type="primary" :loading="submitting" :disabled="locked || !requiredComplete" @click="emit('submit')">确认并提交</van-button>
      </div>
    </div>
  </van-popup>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import StandardField from './StandardField.vue'
import QualityList from './QualityList.vue'
import type { ChangeLog, DemandForm, ElementStatus, Standard, StandardField as StandardFieldDefinition } from '@/api/demand'
import { allFields, fieldPath, readField } from '@/utils/form'
import { fmtTime } from '@/utils/format'
import { ZONE_META } from '@/utils/zones'
const props = withDefaults(defineProps<{
  show: boolean; standard: Standard | null; form: DemandForm; quality: ElementStatus[]; labels: Record<string, string>
  changeLogs?: ChangeLog[]; revision?: number; draftId?: number | null; locked?: boolean; businessConfirmed?: boolean
  flash?: Set<string>; requiredComplete?: boolean; saving?: boolean; submitting?: boolean
}>(), { changeLogs: () => [], revision: 0, draftId: null, locked: false, businessConfirmed: false, flash: () => new Set(), requiredComplete: false, saving: false, submitting: false })
const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'update-field', field: StandardFieldDefinition, value: unknown): void
  (event: 'save'): void
  (event: 'submit'): void
}>()
const expanded = ref<string[]>([])
const statusExpanded = ref<string[]>([])
const zoneGroups = computed(() => {
  if (!props.standard) return []
  const fields = props.standard.elements.filter(field => !field.system && field.zone)
  return ZONE_META.map(meta => ({ ...meta, fields: fields.filter(field => field.zone === meta.zone) }))
})
const plainFields = computed(() => {
  if (!props.standard) return []
  return [...props.standard.elements, ...props.standard.commonFields]
    .filter(field => !field.system && !field.zone)
    .filter(field => props.form.demandTypeCode || !fieldPath(field).startsWith('ext.'))
})
const extraFields = computed(() => {
  if (!props.standard || !props.form.demandTypeCode) return []
  const subtype = String(props.form.ext.techSubtype || '')
  return [...props.standard.optionalFields, ...(props.standard.subtypeFields[subtype] || [])]
})
const SOURCE_LABELS: Record<string, string> = { user: '你填写', agent: 'AI 提炼', default: '默认' }
const labelOf = computed(() => new Map((props.standard ? allFields(props.standard) : []).map(field => [fieldPath(field), field.label])))
const sourceRows = computed(() => {
  return Object.entries(props.form.fieldSources).map(([path, source]) => ({ path, label: labelOf.value.get(path) || path, sourceLabel: SOURCE_LABELS[source] || source, tagType: (source === 'user' ? 'primary' : source === 'agent' ? 'success' : 'default') as 'primary' | 'success' | 'default' }))
})
// 变更留痕字段名：fieldKey 是要素路径（elements.B.businessGoal），映射标准中文标签；判型类扩展路径给白话名
function logLabel(fieldKey: string) {
  if (labelOf.value.has(fieldKey)) return labelOf.value.get(fieldKey)!
  if (fieldKey.includes('typeRecognition')) return '需求类型判型'
  return fieldKey
}
function display(value: unknown) { return value == null || value === '' ? '空' : typeof value === 'object' ? JSON.stringify(value) : String(value) }
</script>
<style scoped>
.full-form { display: flex; flex-direction: column; height: 100%; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 16px 8px; }
.sheet-body { flex: 1; min-height: 0; overflow-y: auto; padding-bottom: 8px; }
.degrade-tip { font-size: 12px; color: #888; padding: 0 16px; margin: 0; }
.form-card { background: #fff; margin: 12px 12px 0; border-radius: 12px; overflow: hidden; border: 1px solid #edf0f5; }
.zone-header { display: flex; align-items: baseline; gap: 8px; padding: 14px 16px 4px; flex-wrap: wrap; }
.zone-header strong { font-size: 14px; color: #1f3a8a; }
.zone-header small { font-size: 11px; color: #999; font-weight: 400; }
.quality-card { padding: 16px; }
.status-card h3 { font-size: 13px; margin: 10px 16px 6px; color: #555; }
.status-row { display: flex; align-items: center; gap: 10px; font-size: 12px; padding: 4px 16px; margin: 0; }
.status-row .path { color: #555; flex-shrink: 0; max-width: 40%; overflow-wrap: anywhere; }
.status-row .diff { color: #888; overflow-wrap: anywhere; }
.status-row small { color: #bbb; margin-left: auto; flex-shrink: 0; }
.sheet-actions { display: flex; gap: 12px; padding: 10px 16px max(12px, env(safe-area-inset-bottom)); background: #fff; border-top: 1px solid #ebedf0; }
.sheet-actions .van-button { flex: 1; }
.ai-flash :deep(.van-field) { animation: flash 2.2s ease-out; }
@keyframes flash { from { background: #e6f3ff; } to { background: #fff; } }
</style>
