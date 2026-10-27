<template>
  <div v-if="groups.length" class="snapshot-card">
    <div class="card-title" @click="collapsed = !collapsed">
      <van-icon name="description" />
      <span>需求要素表单（实时）</span>
      <small v-if="collapsed && isLight"><i class="mode-pill">轻量</i>必填 {{ lightFilled }}/{{ LIGHT_FIELD_KEYS.length }}</small>
      <small v-else-if="collapsed">必填 {{ baseFilled }}/{{ baseTotal }}</small>
      <small v-else>{{ isLight ? '轻量提报 · ' : '' }}点任意一项可直接修改</small>
      <van-icon :name="collapsed ? 'arrow-down' : 'arrow-up'" class="fold" />
    </div>
    <button v-if="recognition && !collapsed" type="button" class="type-row" :disabled="disabled" @click="emit('edit-type')">
      <van-tag :type="typeLabel === '业务需求' ? 'danger' : 'primary'" plain>归类：{{ typeLabel }}</van-tag>
      <!-- 白话副标题（2026-10-27 第三轮拍板）：三级术语标签保留（受理侧口径一致），旁边一句白话说清含义 -->
      <small>{{ typePlainLabel }}</small>
      <!-- 方案④口径显性化：归类与口径两把尺子并排可见，用户不再困惑「同为功能需求待遇为何不同」 -->
      <van-tag :type="isLight ? 'warning' : 'default'" plain>{{ isLight ? '轻量提报' : '常规提报' }}</van-tag>
      <small>{{ recognition.confirmed ? '已确认' : 'AI 判断' }} · 点我可改</small>
    </button>
    <template v-if="!collapsed">
    <div v-for="group in groups" :key="group.zone" class="zone">
      <div class="zone-title" :data-zone="group.zone">
        <span class="zone-pill">{{ group.title }}</span>
        <small>{{ group.note }}</small>
        <!-- B 区空缺标记（2026-10-26 拍板统一必填）：非业务判型——B 区不拦提交，空缺时灰字提示
             「先空着，不影响提交」，不挂待办不标红；判型归业务需求 B1~B4 动态必填，标星计进度，
             不再显示该标记 -->
        <van-tag v-if="group.zone === 'B' && bizGoalEmpty && !bizZoneRequired" type="default" plain>先空着，不影响提交</van-tag>
      </div>
      <button v-for="field in group.fields" :key="fieldPath(field)" type="button" class="el" :disabled="disabled" @click="emit('edit-field', field)">
        <span class="nm">
          <van-icon :name="filled(field) ? 'checked' : isRequired(field) ? 'clock-o' : 'edit'" :color="filled(field) ? '#16a34a' : isRequired(field) ? '#d97706' : '#94a3b8'" size="14" />
          <span class="label">{{ field.label }}<small v-if="field.key === 'businessGoal'" class="plain">对组织的好处</small><i v-if="isRequired(field)" class="req">*</i></span>
        </span>
        <span class="side">
          <span v-if="summary(field)" class="val">{{ summary(field) }}</span>
          <span class="pill" :class="filled(field) ? 'ok' : isRequired(field) ? 'missing' : 'optional'">{{ filled(field) ? '已填' : isRequired(field) ? '待补充' : '选填' }}</span>
        </span>
      </button>
    </div>
    </template>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DemandForm, ElementStatus, Standard, StandardField, TypeRecognition } from '@/api/demand'
import { demandModeOf, recognitionLevelOf } from '@/api/demand'
import { fieldPath, readField } from '@/utils/form'
import { ZONE_META } from '@/utils/zones'
const props = withDefaults(defineProps<{
  standard: Standard | null; form: DemandForm; quality?: ElementStatus[]; businessConfirmed?: boolean; disabled?: boolean; defaultExpanded?: boolean
}>(), { quality: () => [], businessConfirmed: false, disabled: false, defaultExpanded: false })
const emit = defineEmits<{ (event: 'edit-field', field: StandardField): void; (event: 'edit-type'): void }>()
// 默认折叠：要素区与归类行是专业视图，普通用户只看"必填 X/Y"进度，点标题栏展开后改判入口可见
const collapsed = ref(!props.defaultExpanded)
// 基础必填分开计数，折叠态头部显示「必填 X/Y」：A/C/D 12 项所有需求都要；
// 判型归业务需求（2026-10-26 拍板统一必填）B1~B4 动态必填一并计入，非业务判型/轻量不计
const baseRequiredFields = computed(() => groups.value.flatMap(group => group.fields).filter(field => isRequired(field)))
const baseTotal = computed(() => baseRequiredFields.value.length)
const baseFilled = computed(() => baseRequiredFields.value.filter(field => filled(field)).length)
// B 区动态必填判定（对齐服务端 dynamic_required_keys 统一必填口径）：判型归业务需求且非轻量 →
// B1~B4 必填标星计进度；非业务判型 B 区不拦提交，维持「先空着」解耦口径（isLight 惰性求值，定义在下方）
const bizZoneRequired = computed(() => props.businessConfirmed && !isLight.value)
// B 区空缺判定：业务目标（B1）未填即视为 B 区空缺，驱动「先空着，不影响提交」灰字标记
const bizGoalEmpty = computed(() => {
  const goal = groups.value.flatMap(group => group.fields).find(field => field.key === 'businessGoal')
  return goal ? !filled(goal) : false
})
// 微需求快速通道（方案②）：AI 判 mode=light（换 logo/调样式等小需求）时折叠态显示「轻量提报 X/3」，
// 最小集只数（标题/紧急程度/期望效果），其余要素不标星不算进度，与后端 LIGHT_REQUIRED_KEYS 同口径；
// 2026-10-19 拍板：原文（content）移出最小集——系统提取项，非用户提供项
const isLight = computed(() => demandModeOf(props.form) === 'light')
const LIGHT_FIELD_KEYS = ['title', 'urgency', 'acceptanceCriteria']
const lightFilled = computed(() => LIGHT_FIELD_KEYS.filter(key => {
  const field = groups.value.flatMap(group => group.fields).find(item => item.key === key)
  return field ? filled(field) : false
}).length)
// 判型归类标签（方案A：AI 自动判型生效，用户可点开改判）；未产生判型数据时不渲染
const recognition = computed(() => ((props.form.ext?.typeRecognition as TypeRecognition | undefined) || null))
// 归类标签（2026-10-26 拍板派生制）：统一走 recognitionLevelOf——confirmed 人工定稿优先，
// 新结构 level 直读，旧票数结构兼容折算；无生效层级时不渲染标签
const RECOGNITION_LABELS = { business: '业务需求', user: '用户需求', function: '功能需求' } as const
const typeLabel = computed(() => {
  const level = recognitionLevelOf(recognition.value)
  return level ? RECOGNITION_LABELS[level] : ''
})
// 归类白话副标题（2026-10-27 第三轮拍板）：纯业务提报人看不懂三级术语——标签保留（受理侧口径一致），
// 副标题用大白话解释这一级是什么意思；与服务端 FIELD_LABEL_PLAIN 同口径的前端本地副本
const RECOGNITION_PLAIN = { business: '对组织有好处', user: '具体做事的人受益', function: '系统功能改动' } as const
const typePlainLabel = computed(() => {
  const level = recognitionLevelOf(recognition.value)
  return level ? RECOGNITION_PLAIN[level] : ''
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
// B 区统一必填（2026-10-26 拍板）：判型归业务需求 B1~B4 动态必填标星（与服务端 dynamic_required_keys
// 同口径），非业务判型 B 区不标星不拦提交，空缺灰字提示；
// light 模式只标最小集 4 项（C/D 其余不追问不标星，2026-10-11 方案②拍板）。
// 胶囊三态同口径（2026-10-11 拍板）：必填未填=「待补充」琥珀时钟（系统在等）；选填未填=「选填」灰铅笔
// （想填就点，不催促），避免选填项挂假待办、与打回状态「待补充」角标撞词
const B_ZONE_DYNAMIC_KEYS = ['businessGoal', 'businessBackground', 'businessValue', 'stakeholders']
function isRequired(field: StandardField): boolean {
  if (field.system) return false
  if (isLight.value) return LIGHT_FIELD_KEYS.includes(field.key)
  if (field.zone === 'B') return bizZoneRequired.value && B_ZONE_DYNAMIC_KEYS.includes(field.key)
  return !!field.required
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
/* 折叠态轻量口径迷你标签（方案②）：与展开态「轻量提报」warning 标签同琥珀色系，去掉文本拼接的「·」 */
.card-title small .mode-pill { font-style: normal; display: inline-block; background: #fff7e6; color: #d48806; border-radius: 4px; padding: 0 4px; font-size: 10px; line-height: 14px; margin-right: 4px; vertical-align: 1px; }
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
/* businessGoal 白话副标题（2026-10-27 第三轮拍板）：与 .type-row/.zone-title 的 small 同色系 */
.label .plain { color: #94a3b8; font-size: 11px; font-weight: 400; margin-left: 4px; }
.req { color: #dc2626; font-style: normal; font-weight: 700; }
.side { display: flex; align-items: center; gap: 6px; min-width: 0; }
.val { color: #94a3b8; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 140px; }
.pill { border-radius: 10px; padding: 1px 7px; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.pill.ok { background: #dcfce7; color: #14532d; }
.pill.missing { background: #fef3c7; color: #92400e; }
.pill.optional { background: #f1f5f9; color: #64748b; }
</style>
