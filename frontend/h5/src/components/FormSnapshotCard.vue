<template>
  <div v-if="groups.length" class="snapshot-card">
    <div class="card-title" @click="collapsed = !collapsed">
      <van-icon name="description" />
      <span>需求要素表单（实时）</span>
      <small v-if="collapsed">必填 {{ baseFilled }}/{{ baseTotal }}<template v-if="businessConfirmed"> · 业务 {{ bizFilled }}/{{ bizTotal }}</template></small>
      <small v-else>点任意一项可直接修改</small>
      <van-icon :name="collapsed ? 'arrow-down' : 'arrow-up'" class="fold" />
    </div>
    <button v-if="recognition && !collapsed" type="button" class="type-row" :disabled="disabled" @click="emit('edit-type')">
      <van-tag :type="typeLabel === '业务需求' ? 'danger' : 'primary'" plain>归类：{{ typeLabel }}</van-tag>
      <small>{{ recognition.confirmed ? '已确认' : 'AI 判断' }} · 点我可改</small>
    </button>
    <template v-if="!collapsed">
    <div v-for="group in groups" :key="group.zone" class="zone">
      <div class="zone-title" :data-zone="group.zone">
        <span class="zone-pill">{{ group.title }}</span>
        <small>{{ group.note }}</small>
        <van-tag v-if="group.zone === 'B' && businessConfirmed" type="danger" plain>业务需求 · 必填</van-tag>
      </div>
      <button v-for="field in group.fields" :key="fieldPath(field)" type="button" class="el" :disabled="disabled" @click="emit('edit-field', field)">
        <span class="nm">
          <van-icon :name="filled(field) ? 'checked' : 'clock-o'" :color="filled(field) ? '#16a34a' : '#d97706'" size="14" />
          <span class="label">{{ field.label }}<i v-if="isRequired(field)" class="req">*</i></span>
        </span>
        <span class="side">
          <span v-if="summary(field)" class="val">{{ summary(field) }}</span>
          <span class="pill" :class="filled(field) ? 'ok' : 'missing'">{{ filled(field) ? '已填' : '待补充' }}</span>
        </span>
      </button>
    </div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DemandForm, ElementStatus, Standard, StandardField, TypeRecognition } from '@/api/demand'
import { fieldPath, readField } from '@/utils/form'
import { ZONE_META } from '@/utils/zones'
const props = withDefaults(defineProps<{
  standard: Standard | null; form: DemandForm; quality?: ElementStatus[]; businessConfirmed?: boolean; disabled?: boolean; defaultExpanded?: boolean
}>(), { quality: () => [], businessConfirmed: false, disabled: false, defaultExpanded: false })
const emit = defineEmits<{ (event: 'edit-field', field: StandardField): void; (event: 'edit-type'): void }>()
// 默认折叠：要素区与归类行是专业视图，普通用户只看"必填 X/Y"进度，点标题栏展开后改判入口可见
const collapsed = ref(!props.defaultExpanded)
// 基础必填（A/C/D 12 项，所有需求都要）与 B 区业务必填（仅业务需求激活）分开计数，
// 折叠态头部分别显示「必填 X/12 · 业务 Y/4」，与后端追问顺序（先 A/C/D 后 B）口径一致
const baseRequiredFields = computed(() => groups.value.flatMap(group => group.fields).filter(field => field.required && !field.system && field.zone !== 'B'))
const bizRequiredFields = computed(() => groups.value.flatMap(group => group.fields).filter(field => field.required && !field.system && field.zone === 'B'))
const baseTotal = computed(() => baseRequiredFields.value.length)
const baseFilled = computed(() => baseRequiredFields.value.filter(field => filled(field)).length)
const bizTotal = computed(() => bizRequiredFields.value.length)
const bizFilled = computed(() => bizRequiredFields.value.filter(field => filled(field)).length)
// 判型归类标签（方案A：AI 自动判型生效，用户可点开改判）；未产生判型数据时不渲染
const recognition = computed(() => ((props.form.ext?.typeRecognition as TypeRecognition | undefined) || null))
// 归类标签三档（2026-10-10 用户拍板）：confirmed 定稿优先；否则按置信度占优层显示（business 占优→业务需求，user 最高→用户需求，function 最高/并列→功能需求）
const typeLabel = computed(() => {
  const value = recognition.value
  if (!value) return ''
  const confirmed = value.confirmed
  if (confirmed === 'business') return '业务需求'
  if (confirmed === 'user') return '用户需求'
  if (confirmed === 'function') return '功能需求'
  if (props.businessConfirmed) return '业务需求'
  const user = value.user ?? 0
  const fn = value.function ?? 0
  return user > fn ? '用户需求' : '功能需求'
})
// A/B/C/D 分区（术语+白话注释）；无分区的标准（MATL/TRAIN）退化为单组平铺；system 快照要素不渲染
const groups = computed(() => {
  if (!props.standard) return []
  const fields = props.standard.elements.filter(field => !field.system)
  const zoned = ZONE_META.map(meta => ({ ...meta, fields: fields.filter(field => field.zone === meta.zone) })).filter(group => group.fields.length)
  if (zoned.length) return zoned
  const flat = fields.filter(field => !field.zone)
  return flat.length ? [{ zone: 'A' as const, title: '需求要素', note: '', fields: flat }] : []
})
const qualityMap = computed(() => new Map(props.quality.map(element => [element.key, element.status])))
// 红星标记必填项：A/C/D 基础 12 项（标题/类型/子类/紧急程度/原文 + C 区 4 项 + D 区 3 项）始终标星；
// B 区 4 项仅在业务需求（businessConfirmed）时同为必填、也标星，与后端提交门槛同口径
function isRequired(field: StandardField): boolean {
  if (!field.required || field.system) return false
  return field.zone === 'B' ? props.businessConfirmed : true
}
function filled(field: StandardField): boolean {
  const status = qualityMap.value.get(field.key)
  if (status) return status === 'OK' || status === 'VAGUE'
  const value = readField(props.form, field)
  return !(value == null || value === '' || (Array.isArray(value) && !value.length))
}
// 枚举值映射选项中文名（TECH→科技需求、NORMAL→普通），未命中选项时原样展示
function displayValue(field: StandardField, raw: unknown): string {
  return field.options?.[String(raw)] || String(raw)
}
function summary(field: StandardField): string {
  const value = readField(props.form, field)
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return ''
  const text = Array.isArray(value) ? value.map(item => displayValue(field, item)).join('、') : displayValue(field, value)
  return text.length > 32 ? text.slice(0, 32) + '…' : text
}
</script>
<style scoped>
.snapshot-card { background: #fff; border: 1px solid #e5e9f2; border-radius: 12px; padding: 10px 12px; margin-top: 8px; }
.card-title { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; color: #1f3a8a; margin-bottom: 6px; cursor: pointer; user-select: none; }
.card-title small { font-weight: 400; color: #999; margin-left: auto; }
.card-title .fold { color: #94a3b8; }
.type-row { display: flex; align-items: center; gap: 6px; border: 0; background: none; padding: 2px 0 6px; cursor: pointer; }
.type-row small { color: #94a3b8; font-size: 11px; }
.type-row:disabled { cursor: default; }
.zone { border: 1px solid #edf0f5; border-radius: 10px; padding: 7px 10px; margin-top: 7px; background: #fafbfd; }
.zone-title { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.zone-title small { color: #94a3b8; font-size: 11px; }
.zone-pill { font-size: 11px; font-weight: 700; border-radius: 8px; padding: 1px 7px; }
.zone-title[data-zone='A'] .zone-pill { background: #e2e8f0; color: #334155; }
.zone-title[data-zone='B'] .zone-pill { background: #e0e7ff; color: #3730a3; }
.zone-title[data-zone='C'] .zone-pill { background: #fce7f3; color: #9d174d; }
.zone-title[data-zone='D'] .zone-pill { background: #dcfce7; color: #14532d; }
.el { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; border: 0; background: none; padding: 3px 0; font-size: 12.5px; color: #334155; border-bottom: 1px dashed #e8edf3; text-align: left; cursor: pointer; }
.el:last-child { border-bottom: none; }
.el:disabled { cursor: default; }
.nm { display: flex; align-items: center; gap: 5px; min-width: 0; flex-shrink: 0; }
.req { color: #dc2626; font-style: normal; font-weight: 700; }
.side { display: flex; align-items: center; gap: 6px; min-width: 0; }
.val { color: #94a3b8; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px; }
.pill { border-radius: 10px; padding: 1px 7px; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.pill.ok { background: #dcfce7; color: #14532d; }
.pill.missing { background: #fef3c7; color: #92400e; }
</style>
