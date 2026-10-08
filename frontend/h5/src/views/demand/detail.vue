<template>
  <app-layout title="需求详情" show-back>
    <van-loading v-if="loading" class="page-loading">加载详情…</van-loading>
    <template v-else-if="detail">
      <div class="detail-card header"><div class="number">{{ demand.demandNo || `草稿 #${demand.id}` }}</div><h1>{{ demand.title || '未命名草稿' }}</h1><div class="tags"><van-tag type="primary" plain>{{ statusLabel(demand.status) }}</van-tag><van-tag plain>{{ detail.standard?.name || typeLabel(demand.demandTypeCode) }}</van-tag><van-tag :type="demand.urgency === 'NORMAL' ? 'default' : 'danger'">{{ urgencyLabel(demand.urgency) }}</van-tag></div><div class="meta"><span>期望交付：{{ demand.expectDeliveryAt || '未填写' }}</span><span>{{ demand.status === 'DRAFT' ? '保存' : '提交' }}时间：{{ fmtTime(demand.submittedAt || demand.updatedAt) }}</span><span v-if="demand.submitterName">提报人：{{ demand.submitterName }} {{ demand.submitterDept || '' }}</span></div></div>
      <div class="detail-card"><h2>需求概述</h2><template v-if="overviewRows.length"><div v-for="row in overviewRows" :key="row.key" class="ov-row"><strong>{{ row.label }}</strong><p>{{ row.text }}</p></div></template><template v-else><p class="content">{{ demand.content || '尚未填写' }}</p><template v-if="userSupplements.length"><h3 class="supp-title">后续对话中的补充原话</h3><div v-for="m in userSupplements" :key="m.id" class="supp-row"><small>{{ fmtTime(m.createdAt) }}</small><p>{{ m.content }}</p></div></template></template></div>
      <div v-if="detail.messages.length" class="detail-card playback"><van-collapse v-model="expanded"><van-collapse-item title="AI 对话回放" name="messages"><div v-for="message in detail.messages" :key="message.id" class="history-row"><strong>{{ message.role === 'USER' ? '你' : 'AI 提报助手' }}</strong><small>{{ fmtTime(message.createdAt) }}</small><p>{{ message.content }}</p></div></van-collapse-item></van-collapse></div>
      <template v-for="group in zoneGroups" :key="group.zone">
        <div v-if="group.rows.length" class="detail-card"><h2>{{ group.title }}</h2><div v-for="item in group.rows" :key="item.path" class="ext-row"><strong>{{ item.label }}</strong><span>{{ item.value }}</span></div></div>
      </template>
      <div v-if="extensionFields.length" class="detail-card"><h2>补充信息</h2><div v-for="item in extensionFields" :key="item.path" class="ext-row"><strong>{{ item.label }}</strong><span>{{ item.value }}</span></div></div>
      <div class="detail-card playback"><van-collapse v-model="expanded"><van-collapse-item title="E 区 · 状态信息" name="zoneE"><div class="ext-row"><strong>修改次数</strong><span>{{ demand.revision }}</span></div><div v-for="row in sourceRows" :key="row.path" class="ext-row"><strong>{{ row.label }}</strong><span><van-tag :type="row.tagType" plain>{{ row.sourceLabel }}</van-tag></span></div><template v-if="demand.changeLogs.length"><h3 class="log-title">变更留痕</h3><div v-for="log in demand.changeLogs" :key="log.id" class="ext-row log"><strong>{{ logLabel(log.fieldKey) }}</strong><span>{{ display(log.oldValue) }} → {{ display(log.newValue) }}<small>{{ sourceLabel(log.source) }} · {{ fmtTime(log.createdAt) }}</small></span></div></template></van-collapse-item></van-collapse></div>
      <div class="detail-card playback"><van-collapse v-model="expanded"><van-collapse-item title="信息完备度" name="quality"><quality-list :elements="detail.quality" :labels="labels" /></van-collapse-item></van-collapse></div>
      <div v-if="demand.status === 'CLOSED'" class="detail-card"><h2>撤销说明</h2><p class="content">{{ demand.closeReason }}</p><small>{{ fmtTime(demand.closedAt) }}</small></div>
      <div class="detail-card actions">
        <van-button block plain type="primary" :loading="downloading" @click="download">下载 Markdown</van-button>
        <van-button v-if="own && demand.status === 'DRAFT'" block type="primary" @click="router.push({ path: '/report', query: { draftId: demand.id } })">继续编辑草稿</van-button>
        <van-button v-if="own && (demand.status === 'SUBMITTED' || demand.status === 'DRAFT')" block plain type="danger" @click="closeVisible = true">{{ demand.status === 'DRAFT' ? '撤销草稿' : '撤销需求' }}</van-button>
        <van-button block plain @click="router.push(user.userInfo?.isAdmin && !own ? '/admin' : '/mine')">{{ user.userInfo?.isAdmin && !own ? '返回需求整理' : '返回我的需求' }}</van-button>
      </div>
    </template>
    <van-empty v-else description="详情加载失败"><van-button size="small" type="primary" @click="fetchDetail">重试</van-button></van-empty>
    <van-dialog v-model:show="closeVisible" :title="detail?.demand.status === 'DRAFT' ? '撤销草稿' : '撤销需求'" show-cancel-button :before-close="beforeClose"><van-field v-model="reason" type="textarea" rows="3" label="撤销原因" maxlength="256" placeholder="请填写撤销原因" /></van-dialog>
  </app-layout>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import QualityList from '@/components/QualityList.vue'
import { getDemand, closeDemand, downloadMarkdown, type DemandDetail, type StandardField } from '@/api/demand'
import { useUserStore } from '@/store/user'
import { allFields, fieldPath, readField } from '@/utils/form'
import { fmtTime, statusLabel, typeLabel, urgencyLabel } from '@/utils/format'
const route = useRoute(); const router = useRouter(); const user = useUserStore()
const detail = ref<DemandDetail | null>(null); const loading = ref(true); const downloading = ref(false)
const expanded = ref<string[]>([]); const closeVisible = ref(false); const reason = ref('')
const demand = computed(() => detail.value!.demand)
// 需求概述：AI 每轮基于最新表单重写的四段式摘要（ext.overview），固定顺序固定标签；旧草稿无概述时回退展示 A8 原文与补充原话
const OVERVIEW_LABELS: Record<string, string> = { problem: '问题/机会', userScene: '用户&场景', goal: '目标&期望效果', acceptance: '验收标准' }
const overviewRows = computed(() => {
  const overview = ((demand.value?.ext?.overview || {}) as Record<string, unknown>)
  return Object.entries(OVERVIEW_LABELS).filter(([key]) => typeof overview[key] === 'string' && overview[key]).map(([key, label]) => ({ key, label, text: String(overview[key]) }))
})
// 提报人补充原话（方案乙：展示层聚合，A8 底稿不动）：排除与 content 全等的首条 USER 消息（即 A8 底稿），其余用户消息按时间序
const userSupplements = computed(() => {
  if (!detail.value) return []
  const base = (demand.value.content || '').trim()
  let skipped = false
  return detail.value.messages.filter(m => {
    if (m.role !== 'USER') return false
    if (!skipped && base && m.content.trim() === base) { skipped = true; return false }
    return true
  })
})
const own = computed(() => demand.value.submitterId === user.userInfo?.id)
const labels = computed(() => Object.fromEntries((detail.value?.standard ? allFields(detail.value.standard) : []).map(field => [field.key, field.label])))
function display(value: unknown) { return value == null || value === '' ? '空' : Array.isArray(value) ? value.join('、') : typeof value === 'object' ? JSON.stringify(value) : String(value) }
const SOURCE_LABELS: Record<string, string> = { user: '你填写', agent: 'AI 提炼', default: '默认' }
const sourceLabel = (source: string) => SOURCE_LABELS[source] || source
// 五区展示（PRD §4.1 详情页要求）：按 A/B/C/D 分组呈现已填要素；ext 为 MATL/TRAIN 与兼容字段兜底
const ZONE_TITLES = { A: 'A · 公共要素', B: 'B · 业务需求（Why）', C: 'C · 用户需求（Who/What）', D: 'D · 功能需求（How）' } as const
const zoneGroups = computed(() => {
  if (!detail.value?.standard) return []
  const fields = allFields(detail.value.standard).filter(field => fieldPath(field).startsWith('elements.'))
  return Object.entries(ZONE_TITLES).map(([zone, title]) => ({
    zone, title,
    rows: fields.filter(field => field.zone === zone).map(field => {
      const raw = readField(demand.value, field)
      if (raw == null || raw === '' || (Array.isArray(raw) && !raw.length)) return null
      return { path: fieldPath(field), label: field.label, value: field.options?.[String(raw)] || display(raw) }
    }).filter((item): item is { path: string; label: string; value: string } => item !== null)
  }))
})
const sourceRows = computed(() => {
  if (!detail.value) return []
  const labelOf = new Map((detail.value.standard ? allFields(detail.value.standard) : []).map(field => [fieldPath(field), field.label]))
  return Object.entries(demand.value.fieldSources || {}).map(([path, source]) => ({ path, label: labelOf.get(path) || path, source, sourceLabel: sourceLabel(source), tagType: (source === 'user' ? 'primary' : source === 'agent' ? 'success' : 'default') as 'primary' | 'success' | 'default' }))
})
// 变更留痕字段名：fieldKey 是要素路径（elements.B.businessGoal），映射标准中文标签；判型类扩展路径给白话名
const logLabelOf = computed(() => new Map((detail.value?.standard ? allFields(detail.value.standard) : []).map(field => [fieldPath(field), field.label])))
function logLabel(fieldKey: string) {
  if (logLabelOf.value.has(fieldKey)) return logLabelOf.value.get(fieldKey)!
  if (fieldKey.includes('typeRecognition')) return '需求类型判型'
  return fieldKey
}
const extensionFields = computed(() => {
  if (!detail.value) return []
  const standard = detail.value.standard
  const fields: StandardField[] = standard ? allFields(standard).filter(field => fieldPath(field).startsWith('ext.')) : Object.keys(demand.value.ext || {}).map(key => ({ key, label: key, path: `ext.${key}`, kind: 'text' as const }))
  return fields.map(field => { const value = readField(demand.value, field); return { path: fieldPath(field), label: field.label, value: field.options?.[String(value)] || (value == null || value === '' ? '未填写' : String(value)) } }).filter(item => item.value !== '未填写')
})
async function fetchDetail() { loading.value = true; try { detail.value = await getDemand(Number(route.params.id)) } catch { detail.value = null } finally { loading.value = false } }
async function download() { downloading.value = true; try { await downloadMarkdown(demand.value.id, demand.value.demandNo || `draft-${demand.value.id}`) } catch (error) { showToast(error instanceof Error ? error.message : '下载失败') } finally { downloading.value = false } }
async function beforeClose(action: string): Promise<boolean> {
  if (action === 'cancel') return true
  if (!reason.value.trim()) { showToast('请填写撤销原因'); return false }
  try { await closeDemand(demand.value.id, reason.value.trim()); await fetchDetail(); showToast('需求已撤销'); return true } catch { return false }
}
onMounted(fetchDetail)
</script>
<style scoped>
.page-loading { padding: 60px; text-align: center; }.detail-card { background: #fff; margin: 14px 12px; border-radius: 12px; padding: 18px 16px; }.number { font-size: 12px; color: #888; }.header h1 { font-size: 20px; line-height: 1.6; margin: 8px 0 14px; }.tags { display: flex; gap: 8px; flex-wrap: wrap; }.meta { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; font-size: 12px; color: #888; }h2 { font-size: 15px; margin: 0 0 12px; }.content { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.8; margin: 0; }.ext-row { display: grid; grid-template-columns: 92px 1fr; gap: 12px; margin: 12px 0; font-size: 13px; line-height: 1.7; }.ext-row strong { font-weight: 500; color: #888; min-width: 0; overflow-wrap: anywhere; }.ext-row span { min-width: 0; white-space: pre-wrap; overflow-wrap: anywhere; }.ext-row span small { display: block; color: #bbb; margin-top: 2px; }.log-title { font-size: 13px; color: #555; margin: 14px 0 4px; }.playback { padding: 4px 0; }.history-row { font-size: 13px; line-height: 1.8; border-bottom: 1px solid #eee; padding: 12px 0; }.history-row small { color: #999; margin-left: 10px; }.history-row p { margin: 6px 0; white-space: pre-wrap; overflow-wrap: anywhere; }.supp-title { font-size: 13px; color: #555; margin: 14px 0 4px; border-top: 1px dashed #e5e7eb; padding-top: 12px; }.supp-row { font-size: 13px; line-height: 1.8; margin: 8px 0; }.supp-row small { color: #999; display: block; }.supp-row p { margin: 2px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }.ov-row { margin: 12px 0; }.ov-row strong { display: inline-block; font-size: 12px; font-weight: 600; color: #1f3a8a; background: #eef2ff; border-radius: 4px; padding: 2px 8px; margin-bottom: 4px; }.ov-row p { margin: 0; font-size: 14px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }.actions { display: flex; flex-direction: column; gap: 12px; padding-bottom: max(18px, env(safe-area-inset-bottom)); }
</style>
