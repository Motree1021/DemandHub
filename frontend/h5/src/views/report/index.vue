<template>
  <app-layout :title="draftId ? '编辑需求草稿' : '需求提报'" active-tab="report">
    <van-notice-bar v-if="draftId" :text="`草稿已保存 · 版本 ${revision}${dirty ? ' · 有待保存修改' : ''}`" left-icon="records-o" />
    <van-notice-bar v-if="error" :text="error" color="#9a3412" background="#fff7ed" wrapable />
    <van-loading v-if="initializing" class="page-loading">加载草稿与标准…</van-loading>
    <template v-else>
      <div class="intro"><h2>把需求说清楚，交给团队整理</h2><p>可以先保存不完整草稿，或让 AI 帮你提取与补充。</p><van-button block plain type="primary" icon="chat-o" :loading="saving" :disabled="locked || !standard" @click="openGuide">用 AI 整理当前草稿</van-button></div>
      <div v-if="standard" class="form-card">
        <standard-field v-for="field in primaryFields" :key="fieldPath(field)" :field="field" :model-value="readField(form, field)" :disabled="locked" :class="{ 'ai-flash': flash.has(fieldPath(field)) }" @update:model-value="manualEdit(field, $event)" />
      </div>
      <div v-if="extraFields.length" class="form-card">
        <van-collapse v-model="expanded"><van-collapse-item title="补充信息（选填）" name="extra">
          <standard-field v-for="field in extraFields" :key="fieldPath(field)" :field="field" :model-value="readField(form, field)" :disabled="locked" :class="{ 'ai-flash': flash.has(fieldPath(field)) }" @update:model-value="manualEdit(field, $event)" />
        </van-collapse-item></van-collapse>
      </div>
      <div class="form-card quality-card"><quality-list :elements="quality" :labels="labels" /><p v-if="dirty" class="hint">你有未保存修改，当前质量清单仅供参考。</p></div>
      <div class="form-card action-card">
        <p>提交前请确认表单。必填与格式有效即可提交；质量缺口会保留给整理人员。</p>
        <div class="actions"><van-button block plain type="primary" :loading="saving" :disabled="locked" @click="saveFromButton">保存草稿</van-button><van-button block type="primary" :loading="submitting" :disabled="locked || !requiredComplete || !standard" @click="submit">确认并提交</van-button></div>
        <van-button v-if="conflict" block plain class="reload" @click="reloadAfterConflict">重新读取已保存草稿</van-button>
      </div>
    </template>
    <agent-guide-sheet v-model:show="guideVisible" :demand-id="draftId" :session-id="sessionId" :revision="revision" :prepare="prepareAgent" @busy="agentBusy = $event" @complete="applyAgent" />
  </app-layout>
</template>
<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import StandardFieldView from '@/components/StandardField.vue'
import QualityList from '@/components/QualityList.vue'
import AgentGuideSheet from '@/components/AgentGuideSheet.vue'
import { createDraft, updateDraft, submitDemand, getDemand, getStandard, type DemandEntity, type DemandForm, type Standard, type StandardField as StandardFieldDefinition, type ElementStatus, type DemandDetail } from '@/api/demand'
import { createAgentSession, type GuidePayload } from '@/api/agent'
import { ApiError } from '@/api/request'
import { useUserStore } from '@/store/user'
import { allFields, canApplyRevision, fieldPath, formFromDemand, newForm, readField, writeUserField } from '@/utils/form'
// 模板组件名与标准DTO类型分离。
const StandardField = StandardFieldView
const route = useRoute(); const router = useRouter()
const form = reactive<DemandForm>(newForm())
const standard = ref<Standard | null>(null); const draftId = ref<number | null>(null); const sessionId = ref<number | null>(null)
const revision = ref(0); const dirty = ref(true); const quality = ref<ElementStatus[]>([])
const saving = ref(false); const submitting = ref(false); const agentBusy = ref(false); const initializing = ref(true)
const guideVisible = ref(false); const error = ref(''); const conflict = ref(false); const expanded = ref<string[]>([]); const flash = ref(new Set<string>())
let flashTimer: ReturnType<typeof setTimeout> | undefined
let savePromise: Promise<DemandEntity> | null = null
let savedDemand: DemandEntity | null = null
let createPayload: (DemandForm & { clientRequestId: string }) | null = null
const CREATE_KEY = `demandhub_h5_create_request_${useUserStore().userInfo?.id || 'current'}`
let clientRequestId: string = crypto.randomUUID()
function restoreCreation() {
  const saved = sessionStorage.getItem(CREATE_KEY)
  if (!saved) return
  try {
    const request = JSON.parse(saved) as DemandForm & { clientRequestId: string }
    if (!request.clientRequestId || !request.ext || !request.fieldSources) throw new Error()
    createPayload = request; clientRequestId = request.clientRequestId
    const { clientRequestId: _requestId, ...rest } = request
    Object.assign(form, rest)
  } catch { sessionStorage.removeItem(CREATE_KEY) }
}
function resetNewDraft() {
  Object.assign(form, newForm()); draftId.value = null; sessionId.value = null; revision.value = 0
  quality.value = []; dirty.value = true; savedDemand = null; createPayload = null
  guideVisible.value = false; error.value = ''; conflict.value = false; clientRequestId = crypto.randomUUID()
}
const locked = computed(() => saving.value || submitting.value || agentBusy.value || initializing.value)
const primaryFields = computed(() => standard.value ? [...standard.value.elements, ...standard.value.commonFields].filter(field => form.demandTypeCode || !fieldPath(field).startsWith('ext.')) : [])
const extraFields = computed(() => {
  if (!standard.value || !form.demandTypeCode) return []
  const subtype = String(form.ext.techSubtype || '')
  return [...standard.value.optionalFields, ...(standard.value.subtypeFields[subtype] || [])]
})
const labels = computed(() => Object.fromEntries((standard.value ? allFields(standard.value) : []).map(field => [field.key, field.label])))
const requiredComplete = computed(() => !!form.title?.trim() && !!form.demandTypeCode && !!form.content?.trim())
function snapshot(): DemandForm { return JSON.parse(JSON.stringify(form)) }
function applyDemand(demand: DemandEntity) {
  draftId.value = demand.id; revision.value = demand.revision; sessionId.value = demand.sessionId
  Object.assign(form, formFromDemand(demand)); quality.value = demand.quality || []; savedDemand = demand; dirty.value = false
}
function restoreDetail(detail: DemandDetail) {
  applyDemand(detail.demand)
  if (detail.demand.status !== 'DRAFT') return
  const message = [...(detail.messages || [])].reverse().find(item => item.role === 'ASSISTANT' && item.structuredPayload)
  if (!message?.structuredPayload) return
  try {
    const payload = JSON.parse(message.structuredPayload) as GuidePayload
    if (payload.demandId === detail.demand.id && payload.sessionId === detail.demand.sessionId && payload.revision === detail.demand.revision && Array.isArray(payload.elements)) quality.value = payload.elements
  } catch { /* 草稿没有可用质量快照时保持空清单 */ }
}
let standardGeneration = 0
async function loadStandard(type: string | null) {
  const generation = ++standardGeneration
  standard.value = null
  try { const result = await getStandard(type || 'TECH'); if (generation === standardGeneration) standard.value = result }
  catch { if (generation === standardGeneration) error.value = '需求标准加载失败，请刷新后重试' }
}
function manualEdit(field: StandardFieldDefinition, value: unknown) {
  if (locked.value) return
  const oldType = form.demandTypeCode
  writeUserField(form, field, value); dirty.value = true; error.value = ''
  if (fieldPath(field) === 'demandTypeCode' && oldType !== value) {
    form.ext = {}; Object.keys(form.fieldSources).filter(path => path.startsWith('ext.')).forEach(path => delete form.fieldSources[path])
  }
}
function recordError(value: unknown) {
  error.value = value instanceof Error ? value.message : '操作失败，请重试'
  conflict.value = value instanceof ApiError && value.code === 409
}
async function save(): Promise<DemandEntity> {
  if (savePromise) return savePromise
  if (!dirty.value && savedDemand) return savedDemand
  saving.value = true; error.value = ''
  savePromise = (async () => {
    let demand: DemandEntity
    if (draftId.value) demand = await updateDraft(draftId.value, { ...snapshot(), expectedRevision: revision.value })
    else {
      // 创建失败后的重试保持原ID和原请求内容，避免重复草稿和输入冲突。
      createPayload ||= { ...snapshot(), clientRequestId }
      sessionStorage.setItem(CREATE_KEY, JSON.stringify(createPayload))
      demand = await createDraft(createPayload)
      const { clientRequestId: _requestId, ...originalForm } = createPayload
      const changed = JSON.stringify(snapshot()) !== JSON.stringify(originalForm)
      // 创建结果已确认后先固定id，即使后续更新失败也不会再创建。
      draftId.value = demand.id; revision.value = demand.revision; savedDemand = demand
      sessionStorage.removeItem(CREATE_KEY); createPayload = null
      await router.replace({ path: '/report', query: { draftId: demand.id } })
      // UI在请求期间锁定；恢复原创建请求后，保存后续手改。
      if (changed) demand = await updateDraft(demand.id, { ...snapshot(), expectedRevision: demand.revision })
    }
    applyDemand(demand); conflict.value = false; return demand
  })()
  try { return await savePromise } catch (value) { recordError(value); throw value }
  finally { saving.value = false; savePromise = null }
}
async function saveFromButton() { try { await save(); showToast('草稿已保存，可在“我的需求”继续编辑') } catch { /* 错误已显示 */ } }
async function prepareAgent() {
  const demand = await save()
  if (!sessionId.value) sessionId.value = (await createAgentSession(demand.id)).id
  return { demandId: demand.id, sessionId: sessionId.value, revision: revision.value }
}
async function openGuide() { try { await prepareAgent(); guideVisible.value = true } catch (value) { recordError(value) } }
function applyAgent(payload: GuidePayload) {
  if (payload.demandId !== draftId.value || payload.sessionId !== sessionId.value || !canApplyRevision(revision.value, payload.revision, dirty.value)) {
    showToast('对话已保存，当前表单有更新，未覆盖表单'); return
  }
  const before = snapshot()
  Object.assign(form, { ...payload.structured, fieldSources: payload.fieldSources })
  revision.value = payload.revision; quality.value = payload.elements; dirty.value = false
  if (savedDemand) savedDemand = { ...savedDemand, ...snapshot(), revision: revision.value, quality: payload.elements, sessionId: sessionId.value }
  if (standard.value) flash.value = new Set(allFields(standard.value).filter(field => JSON.stringify(readField(before, field)) !== JSON.stringify(readField(form, field))).map(fieldPath))
  clearTimeout(flashTimer); flashTimer = setTimeout(() => { flash.value = new Set() }, 2200)
}
async function submit() {
  if (locked.value || !requiredComplete.value) return
  try { await showConfirmDialog({ title: '确认提交', message: '请确认表单内容准确。提交后生成正式编号，质量缺口会保留给整理人员。' }) } catch { return }
  submitting.value = true
  try { const demand = await save(); const submitted = await submitDemand(demand.id, revision.value); applyDemand(submitted); await router.replace(`/demand/${submitted.id}`) }
  catch (value) { recordError(value) } finally { submitting.value = false }
}
async function reloadAfterConflict() {
  if (!draftId.value) return
  try { await showConfirmDialog({ title: '重新读取草稿', message: '这会用服务器已保存内容替换当前未保存修改。' }); restoreDetail(await getDemand(draftId.value)); conflict.value = false; error.value = '' }
  catch { /* 取消保持本地修改 */ }
}
let initializationGeneration = 0
async function initialize() {
  const generation = ++initializationGeneration
  initializing.value = true; error.value = ''
  try {
    const id = Number(route.query.draftId)
    if (Number.isSafeInteger(id) && id > 0) {
      const detail = await getDemand(id)
      if (generation !== initializationGeneration) return
      if (detail.demand.status !== 'DRAFT') { await router.replace(`/demand/${id}`); return }
      restoreDetail(detail)
    } else { restoreCreation() }
    await loadStandard(form.demandTypeCode)
  } catch (value) { if (generation === initializationGeneration) recordError(value) } finally { if (generation === initializationGeneration) initializing.value = false }
}
watch(() => form.demandTypeCode, type => { loadStandard(type) })
watch(() => route.query.draftId, () => {
  if (saving.value || submitting.value) return
  resetNewDraft(); initialize()
})
onMounted(initialize)
onBeforeUnmount(() => clearTimeout(flashTimer))
</script>
<style scoped>
.page-loading { text-align: center; padding: 48px; }.intro { padding: 24px 16px 10px; }.intro h2 { font-size: 19px; color: #1f3a8a; margin: 0 0 8px; }.intro p { font-size: 13px; color: #777; margin: 0 0 20px; line-height: 1.7; }.form-card { background: #fff; margin: 14px 12px; border-radius: 12px; overflow: hidden; }.quality-card, .action-card { padding: 16px; }.action-card p, .hint { font-size: 12px; line-height: 1.7; color: #777; margin: 0 0 16px; }.actions { display: flex; gap: 12px; }.actions .van-button { flex: 1; }.reload { margin-top: 12px; }.ai-flash :deep(.van-field) { animation: flash 2.2s ease-out; }@keyframes flash { from { background: #e6f3ff; } to { background: #fff; } }
</style>
