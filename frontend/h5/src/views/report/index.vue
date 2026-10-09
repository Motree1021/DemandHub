<template>
  <app-layout active-tab="report">
    <div class="report-chat">
      <van-notice-bar v-if="draftId" :text="`草稿已保存 · 版本 ${revision}${dirty ? ' · 有待保存修改' : ''}`" left-icon="records-o" />
      <van-notice-bar v-if="error" :text="error" color="#9a3412" background="#fff7ed" wrapable />
      <van-loading v-if="initializing" class="page-loading">加载草稿与标准…</van-loading>
      <template v-else>
        <steps-bar :step="step" />
        <div class="toolbar">
          <button type="button" class="tool" @click="formSheetVisible = true"><van-icon name="description" /> 完整要素表单</button>
          <button type="button" class="tool" :disabled="locked" @click="saveFromButton"><van-icon name="records-o" /> 保存草稿</button>
        </div>
        <div v-if="conflict" class="conflict-bar"><van-button size="small" plain type="primary" @click="reloadAfterConflict">草稿已在别处更新，点此重新读取</van-button></div>
        <agent-chat-panel ref="panelRef" class="chat-main" :demand-id="draftId" :session-id="sessionId" :revision="revision" :prepare="prepareAgent" :standard="standard" :form="form" :quality="quality" :business-confirmed="businessConfirmed" @busy="agentBusy = $event" @complete="applyAgent" @edit-type="typeSheetVisible = true" @edit-field="openFieldEdit" @submit="submit" @save-draft="saveFromButton" @unavailable="onUnavailable">
          <template #welcome>
            <div class="msg-row assistant">
              <div class="ava ag">AI</div>
              <div class="msg-bubble">
                <div class="who">需求收集智能体</div>
                你好，我是科技需求收集智能体，负责帮你把需求提报清楚。你可以直接说一句话诉求、整段粘贴整理好的文字，用输入法语音转文字也行。我会自动拆解成要素表单，缺什么会主动问你。先试试：
                <div class="entry-opts">
                  <button type="button" class="opt primary" @click="focusInput">我有一个清晰的需求要提报（大段粘贴&AI检查）</button>
                  <button type="button" class="opt" @click="examplesVisible = !examplesVisible">看一段话示例，照着写</button>
                  <button type="button" class="opt" @click="sendFuzzy">我只有一个模糊想法（AI会引导你梳理需求）</button>
                </div>
              </div>
            </div>
            <div v-if="examplesVisible" class="msg-row assistant">
              <div class="ava ag">AI</div>
              <div class="msg-bubble">
                <div class="who">需求收集智能体</div>
                <p class="example-tip">把目标、场景、功能、验收写进一段话，我一次就能拆解完整。点「复制示例」粘贴到输入框，改成你自己的需求后发送：</p>
                <div v-for="example in EXAMPLES" :key="example.title" class="example-card">
                  <strong>{{ example.title }}</strong>
                  <p>{{ example.text }}</p>
                  <button type="button" class="opt primary" @click="copyExample(example.text)">复制示例</button>
                </div>
              </div>
            </div>
          </template>
        </agent-chat-panel>
      </template>
      <full-form-sheet v-model:show="formSheetVisible" :standard="standard" :form="form" :quality="quality" :labels="labels" :change-logs="changeLogs" :revision="revision" :draft-id="draftId" :locked="locked" :business-confirmed="businessConfirmed" :flash="flash" :required-complete="requiredComplete" :saving="saving" :submitting="submitting" @update-field="manualEdit" @save="saveFromButton" @submit="submit" />
      <field-edit-sheet v-model:show="fieldEditVisible" :field="editingField" :value="editingValue" @save="onFieldEditSave" />
      <van-action-sheet v-model:show="typeSheetVisible" :actions="typeActions" cancel-text="取消" description="归类影响提交要求：业务需求需补齐业务目标/背景/价值/干系人；日常功能需求 12 项必填齐即可提交。" close-on-click-action @select="onTypeSelect" />
    </div>
  </app-layout>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import StepsBar from '@/components/StepsBar.vue'
import AgentChatPanel from '@/components/AgentChatPanel.vue'
import FullFormSheet from '@/components/FullFormSheet.vue'
import FieldEditSheet from '@/components/FieldEditSheet.vue'
import { createDraft, updateDraft, submitDemand, getDemand, getStandard, type ChangeLog, type DemandEntity, type DemandForm, type Standard, type StandardField as StandardFieldDefinition, type ElementStatus, type DemandDetail, type TypeRecognition } from '@/api/demand'
import { createAgentSession, type GuidePayload } from '@/api/agent'
import { ApiError } from '@/api/request'
import { useUserStore } from '@/store/user'
import { allFields, canApplyRevision, fieldPath, formFromDemand, newForm, readField, writeUserField } from '@/utils/form'
const route = useRoute(); const router = useRouter()
const form = reactive<DemandForm>(newForm())
const standard = ref<Standard | null>(null); const draftId = ref<number | null>(null); const sessionId = ref<number | null>(null)
const revision = ref(0); const dirty = ref(true); const quality = ref<ElementStatus[]>([])
const saving = ref(false); const submitting = ref(false); const agentBusy = ref(false); const initializing = ref(true)
const error = ref(''); const conflict = ref(false); const flash = ref(new Set<string>())
const changeLogs = ref<ChangeLog[]>([]); const formSheetVisible = ref(false)
const fieldEditVisible = ref(false); const editingField = ref<StandardFieldDefinition | null>(null); const editingValue = ref<unknown>(null)
const panelRef = ref<InstanceType<typeof AgentChatPanel> | null>(null)
const lastPayload = ref<GuidePayload | null>(null); const examplesVisible = ref(false)
// 页面标题经 document.title 传给宿主小程序原生导航栏（H5 内不渲染标题栏，避免双标题）
watch(draftId, value => { document.title = value ? '编辑需求草稿' : '需求提报' }, { immediate: true })
// 一段话示例（原型 §示例引导）：覆盖完整型/简洁型两种典型业务需求文本
const EXAMPLES = [
  { title: '示例一 · 完整型（目标/场景/功能/验收都带）', text: '我们部门每天晨会要统计各渠道销量，现在手工从三个系统导数据拼 Excel，要 40 分钟还容易错。希望做一个自动报表，每天早上 8 点前生成，包含各渠道销量明细和排名，自动推送企微群；验收标准是每个交易日 8:00 前生成、数据与核心系统一致。' },
  { title: '示例二 · 简洁型（一句话带核心要素）', text: '客户经理每月要导出客户持仓清单发给客户，希望系统每月末自动生成 Excel 并邮件推送，验收是每月最后一天 18:00 前发出、覆盖全部客户。' },
]
// FR-01/FR-03 判型结果：用户确认（confirmed）优先于模型置信度；业务需求命中后 B 区必填门槛生效（对齐服务端 business_confirmed）
const typeRecognition = computed(() => form.ext.typeRecognition as TypeRecognition | undefined)
const businessConfirmed = computed(() => {
  const recognition = typeRecognition.value
  if (!recognition) return false
  if (recognition.confirmed != null) return recognition.confirmed === 'business'
  return (recognition.business ?? 0) >= 0.5
})
// 步骤条推导：表达→拆解→追问→提交（方案A：判型由 AI 自动生效，无确认步骤）
const step = computed(() => {
  const payload = lastPayload.value
  if (!payload) return 0
  if (payload.canSubmit) return 3
  if (payload.quickReplies?.length || payload.missing?.length || payload.askedTarget) return 2
  return 1
})
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
  error.value = ''; conflict.value = false; clientRequestId = crypto.randomUUID()
  lastPayload.value = null; examplesVisible.value = false; formSheetVisible.value = false
}
const locked = computed(() => saving.value || submitting.value || agentBusy.value || initializing.value)
const labels = computed(() => Object.fromEntries((standard.value ? allFields(standard.value) : []).map(field => [field.key, field.label])))
const requiredComplete = computed(() => !!form.title?.trim() && !!form.demandTypeCode && !!form.content?.trim())
function snapshot(): DemandForm { return JSON.parse(JSON.stringify(form)) }
function applyDemand(demand: DemandEntity) {
  draftId.value = demand.id; revision.value = demand.revision; sessionId.value = demand.sessionId
  Object.assign(form, formFromDemand(demand)); quality.value = demand.quality || []; changeLogs.value = demand.changeLogs || []; savedDemand = demand; dirty.value = false
}
function restoreDetail(detail: DemandDetail) {
  applyDemand(detail.demand)
  if (detail.demand.status !== 'DRAFT') return
  const message = [...(detail.messages || [])].reverse().find(item => item.role === 'ASSISTANT' && item.structuredPayload)
  if (!message?.structuredPayload) return
  try {
    const payload = JSON.parse(message.structuredPayload) as GuidePayload
    if (payload.demandId === detail.demand.id && payload.sessionId === detail.demand.sessionId && payload.revision === detail.demand.revision && Array.isArray(payload.elements)) {
      quality.value = payload.elements
      lastPayload.value = payload
    }
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
function openFieldEdit(field: StandardFieldDefinition) {
  editingField.value = field; editingValue.value = readField(form, field); fieldEditVisible.value = true
}
function onFieldEditSave(field: StandardFieldDefinition, value: unknown) { manualEdit(field, value) }
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
// FR-01 判型改判（方案A：AI 自动判型生效，用户从要素卡「归类」标签打开三选项）：写回 confirmed 并立即保存，下一轮按新门槛追问
const typeSheetVisible = ref(false)
const typeActions = [
  { name: '是业务需求', subname: '涉及业务目标/考核指标，或需要跨部门协作' },
  { name: '只是日常功能需求', subname: '某个系统功能的日常改进' },
  { name: '让 AI 判断', subname: '按对话内容自动判定，随时可再改' },
]
function onTypeSelect(_action: unknown, index: number) { onConfirmType((['business', 'none', null] as const)[index]) }
async function onConfirmType(confirmed: 'business' | 'none' | null) {
  form.ext.typeRecognition = { ...(typeRecognition.value || {}), confirmed }
  form.fieldSources['ext.typeRecognition'] = 'user'
  dirty.value = true
  showToast(confirmed === 'business' ? '已确认为业务需求，「业务目标/背景/价值」纳入必填' : confirmed === 'none' ? '已记录，按日常功能需求继续' : '已恢复 AI 自动判断')
  try { await save() } catch { /* 错误已展示，判型结果保留在表单中可重试 */ }
}
function applyAgent(payload: GuidePayload) {
  if (payload.demandId !== draftId.value || payload.sessionId !== sessionId.value || !canApplyRevision(revision.value, payload.revision, dirty.value)) {
    showToast('对话已保存，当前表单有更新，未覆盖表单'); return
  }
  const before = snapshot()
  Object.assign(form, { ...payload.structured, fieldSources: payload.fieldSources })
  revision.value = payload.revision; quality.value = payload.elements; dirty.value = false
  lastPayload.value = payload
  if (savedDemand) savedDemand = { ...savedDemand, ...snapshot(), revision: revision.value, quality: payload.elements, sessionId: sessionId.value }
  if (standard.value) flash.value = new Set(allFields(standard.value).filter(field => JSON.stringify(readField(before, field)) !== JSON.stringify(readField(form, field))).map(fieldPath))
  clearTimeout(flashTimer); flashTimer = setTimeout(() => { flash.value = new Set() }, 2200)
}
async function submit() {
  if (locked.value || !requiredComplete.value) return
  try { await showConfirmDialog({ title: '确认提交', message: '请确认要素内容准确。提交后生成正式编号，质量缺口会保留给整理人员。' }) } catch { return }
  submitting.value = true
  try {
    const demand = await save(); const submitted = await submitDemand(demand.id, revision.value)
    applyDemand(submitted); showToast(`已提交，需求编号 ${submitted.demandNo || ''}`)
    await router.replace(`/demand/${submitted.id}`)
  }
  catch (value) {
    recordError(value)
    // 逃生口：AI 自动判型（未人工确认）被 B 区必填拦截时，指引改判入口
    if (value instanceof ApiError && value.code === 400 && businessConfirmed.value && typeRecognition.value?.confirmed == null) {
      error.value += ' 若本需求不涉及业务目标/考核，可点要素表单顶部的「归类」标签改判为日常功能需求。'
    }
  }
  finally { submitting.value = false }
}
async function reloadAfterConflict() {
  if (!draftId.value) return
  try { await showConfirmDialog({ title: '重新读取草稿', message: '这会用服务器已保存内容替换当前未保存修改。' }); restoreDetail(await getDemand(draftId.value)); conflict.value = false; error.value = '' }
  catch { /* 取消保持本地修改 */ }
}
function onUnavailable(value: boolean) {
  if (!value) return
  formSheetVisible.value = true
  showToast('AI 暂不可用，可直接填写表单提交')
}
// 欢迎语三入口（对齐原型）：大段粘贴聚焦输入；示例复制后由用户自行编辑发送；模糊想法交给 AI 引导
function focusInput() {
  nextTick(() => (panelRef.value?.$el as HTMLElement | undefined)?.querySelector('textarea')?.focus())
}
// 示例仅作参考：复制到剪贴板，由用户粘贴进输入框自行编辑后发送——不预写 content、不代发消息，避免示例文本占用 A8 原始提报底稿
async function copyExample(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    showToast('已复制，粘贴到输入框编辑后发送')
  } catch {
    showToast('复制失败，请长按示例文本手动复制')
  }
  focusInput()
}
function sendFuzzy() { panelRef.value?.sendMessage('我只有一个模糊想法，请一步步帮我想清楚').catch(recordError) }
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
.report-chat { display: flex; flex-direction: column; height: calc(100dvh - 46px - 66px); }
.page-loading { text-align: center; padding: 48px; }
.toolbar { display: flex; gap: 10px; padding: 8px 12px; background: #fff; border-bottom: 1px solid #ebedf0; }
.tool { display: flex; align-items: center; gap: 4px; border: 0; background: none; color: #1f3a8a; font-size: 13px; padding: 6px 4px; }
.tool:disabled { color: #bbb; }
.conflict-bar { padding: 6px 12px; background: #fff7ed; }
.chat-main { flex: 1; min-height: 0; }
.msg-row { display: flex; gap: 8px; align-items: flex-end; margin: 12px 0; }
.msg-row.assistant { display: flex; }
.ava { width: 28px; height: 28px; border-radius: 9px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.ava.ag { background: #1f3a8a; color: #fff; }
.msg-bubble { background: #fff; border: 1px solid #e5e9f2; border-radius: 12px; border-top-left-radius: 4px; padding: 10px 12px; font-size: 14px; line-height: 1.7; max-width: 88%; overflow-wrap: anywhere; }
.who { font-size: 12px; color: #999; margin-bottom: 3px; }
.entry-opts { display: flex; flex-direction: column; gap: 7px; margin-top: 10px; }
.opt { border: 1px solid #a7b8d8; color: #1f3a8a; background: #fff; border-radius: 16px; padding: 9px 14px; font-size: 13px; text-align: left; line-height: 1.5; min-height: 40px; }
.opt.primary { background: #1f3a8a; border-color: #1f3a8a; color: #fff; }
.opt:disabled { opacity: 0.5; }
.example-tip { font-size: 13px; color: #555; line-height: 1.7; margin: 0 0 10px; }
.example-card { border: 1px solid #c7d2fe; background: #eef2ff; border-radius: 10px; padding: 10px 12px; margin-bottom: 10px; }
.example-card strong { font-size: 13px; color: #3730a3; }
.example-card p { font-size: 13px; line-height: 1.8; color: #444; margin: 8px 0 10px; white-space: pre-wrap; }
.example-card .opt { width: 100%; text-align: center; }
</style>
