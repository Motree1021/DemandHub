<template>
  <div class="chat-panel">
    <van-notice-bar v-if="unavailable" text="AI 暂不可用，可直接打开完整表单手填提交" left-icon="warning-o" wrapable />
    <div ref="msgBox" class="msg-box">
      <slot v-if="!messages.length && !sending" name="welcome" />
      <div v-for="message in messages" :key="message.id" class="msg-row" :class="message.role.toLowerCase()">
        <div class="ava" :class="message.role === 'USER' ? 'me' : 'ag'">{{ message.role === 'USER' ? '我' : 'AI' }}</div>
        <div class="msg-bubble"><div class="who">{{ message.role === 'USER' ? '我' : '需求收集智能体' }}</div>{{ message.content }}</div>
      </div>
      <template v-if="sending">
        <div class="msg-row user"><div class="ava me">我</div><div class="msg-bubble"><div class="who">我</div>{{ pending?.message }}</div></div>
        <div class="msg-row assistant"><div class="ava ag">AI</div><div class="msg-bubble"><div class="who">需求收集智能体</div>{{ partialReply || (thinking ? '正在思考和整理…' : '正在处理…') }}</div></div>
      </template>
      <p v-if="failure" class="failure">{{ failure }}<br>原输入与请求已保留。可重试恢复已保存结果。</p>
      <div v-if="latest?.granularityHint" class="hint-banner">
        <strong>{{ latest.granularityHint.level === 'too_broad' ? '需求有点大，先聚焦' : '需求有点细，补上下文' }}</strong>
        <small>收敛标准：{{ latest.granularityHint.converge }}</small>
      </div>
      <div v-if="latest?.impactHints?.length" class="hint-banner impact">
        <small v-for="hint in latest.impactHints" :key="hint">{{ hint }}</small>
      </div>
      <form-snapshot-card v-if="showSnapshot" :standard="standard" :form="form!" :quality="quality" :business-confirmed="businessConfirmed" :disabled="sending" @edit-field="emit('edit-field', $event)" @edit-type="emit('edit-type')" />
      <div v-if="latest" class="summary">
        <span>{{ latest.canSubmit ? '必填与格式已满足，可确认要素后提交' : '请补充必填或修正格式后提交' }}</span>
        <small v-if="!latest.qualityComplete">信息仍有质量缺口，跳过的内容会标记为待后续补充。</small>
        <small v-if="latest.guidanceComplete && !latest.qualityComplete">本轮引导已结束，可继续手动完善。</small>
      </div>
    </div>
    <div v-if="latest?.canSubmit && !sending" class="chips">
      <button class="primary" @click="emit('submit')">确认提交</button>
      <button @click="emit('save-draft')">先保存草稿，稍后再提交</button>
    </div>
    <div v-if="latest?.quickReplies.length && !sending" class="chips"><button v-for="reply in latest.quickReplies" :key="reply" @click="quickSend(reply)">{{ reply }}</button></div>
    <van-button v-if="pending && !sending" size="small" plain type="primary" @click="retry">重试上一条</van-button>
    <div class="input-row">
      <van-field v-model="input" type="textarea" rows="2" autosize :disabled="sending" placeholder="继续说，或粘贴大段需求…" />
      <van-button type="primary" :loading="sending" :disabled="!input.trim() || unavailable" @click="send">发送</van-button>
    </div>
    <small class="tip">发送前会保存草稿；你明确手改的内容由服务端保护。最终提交内容以要素表单为准。</small>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { agentSessionMessages, guideChatStream, StreamError, type GuidePayload, type GuideRequest } from '@/api/agent'
import type { AgentMessage, DemandForm, ElementStatus, Standard, StandardField } from '@/api/demand'
import { canApplyRevision } from '@/utils/form'
import FormSnapshotCard from './FormSnapshotCard.vue'
const props = withDefaults(defineProps<{
  demandId: number | null; sessionId: number | null; revision: number
  prepare: () => Promise<{ demandId: number; sessionId: number; revision: number }>
  standard?: Standard | null; form?: DemandForm | null; quality?: ElementStatus[]; businessConfirmed?: boolean
}>(), { standard: null, form: null, quality: () => [], businessConfirmed: false })
const emit = defineEmits<{
  (event: 'busy', value: boolean): void
  (event: 'complete', value: GuidePayload): void
  (event: 'edit-type'): void
  (event: 'edit-field', field: StandardField): void
  (event: 'submit'): void
  (event: 'save-draft'): void
  (event: 'unavailable', value: boolean): void
}>()
const messages = ref<AgentMessage[]>([]); const input = ref(''); const sending = ref(false)
const unavailable = ref(false); const failure = ref(''); const partialReply = ref(''); const thinking = ref(false)
const latest = ref<GuidePayload | null>(null); const pending = ref<GuideRequest | null>(null); const msgBox = ref<HTMLElement>()
let controller: AbortController | null = null
let thinkingTimer: ReturnType<typeof setTimeout> | undefined
let historyGeneration = 0
let runGeneration = 0
const pendingKey = () => `demandhub_h5_pending_${props.demandId}`
function persistPending() { if (pending.value) sessionStorage.setItem(pendingKey(), JSON.stringify(pending.value)); else sessionStorage.removeItem(pendingKey()) }
const showSnapshot = computed(() => !!props.standard && !!props.form && messages.value.length > 0)
async function scroll() { await nextTick(); msgBox.value?.scrollTo?.({ top: msgBox.value.scrollHeight, behavior: 'smooth' }) }
function restorePending() {
  try {
    const saved = sessionStorage.getItem(pendingKey())
    if (saved) {
      const request = JSON.parse(saved) as GuideRequest
      if (request.demandId === props.demandId && request.sessionId === props.sessionId) { pending.value = request; input.value = request.message }
    }
  } catch { /* 本地暂存损坏时忽略 */ }
}
async function loadHistory() {
  if (!props.sessionId) return
  const sessionId = props.sessionId; const demandId = props.demandId; const generation = ++historyGeneration
  const history = await agentSessionMessages(sessionId)
  if (generation !== historyGeneration || props.sessionId !== sessionId || props.demandId !== demandId) return
  messages.value = history.filter(message => message.role !== 'SYSTEM')
  const last = [...messages.value].reverse().find(message => message.role === 'ASSISTANT' && message.structuredPayload)
  if (last?.structuredPayload) {
    try {
      const payload = JSON.parse(last.structuredPayload) as GuidePayload
      if (payload.demandId === props.demandId && payload.sessionId === props.sessionId && canApplyRevision(props.revision, payload.revision)) {
        latest.value = payload
        emit('complete', payload)
      }
    } catch { /* 历史文本仍可回放，不使用格式异常的历史表单 */ }
  }
  scroll()
}
async function run(request: GuideRequest) {
  const generation = ++runGeneration
  pending.value = request; persistPending(); sending.value = true; emit('busy', true)
  failure.value = ''; partialReply.value = ''; thinking.value = false
  controller = new AbortController()
  thinkingTimer = setTimeout(() => { thinking.value = true }, 5000)
  try {
    const payload = await guideChatStream(request, { onDelta: delta => { partialReply.value += delta; scroll() }, onProcessing: () => scroll() }, controller.signal)
    if (generation !== runGeneration || props.demandId !== request.demandId || props.sessionId !== request.sessionId) return
    latest.value = payload
    emit('complete', payload)
    pending.value = null; persistPending(); input.value = ''; unavailable.value = false
    try { await loadHistory() } catch { messages.value.push({ id: Date.now(), sessionId: request.sessionId, role: 'ASSISTANT', content: partialReply.value, structuredPayload: JSON.stringify(payload), createdAt: '' }) }
  } catch (error) {
    if (generation !== runGeneration || props.demandId !== request.demandId || props.sessionId !== request.sessionId) return
    input.value = request.message
    // 明确冲突表示这次请求没有成功；下一次同样文字使用最新revision和新requestId。
    if (error instanceof StreamError && error.code === 409) { pending.value = null; persistPending() }
    failure.value = error instanceof Error && error.name === 'AbortError' ? '请求已取消，完成状态尚未确认' : error instanceof Error ? error.message : '发送失败'
    unavailable.value = error instanceof StreamError && error.code === 1401
  } finally {
    clearTimeout(thinkingTimer); sending.value = false; emit('busy', false); controller = null; partialReply.value = ''; scroll()
  }
}
async function send() {
  const message = input.value.trim()
  if (!message || sending.value || unavailable.value) return
  if (pending.value?.message === message) return retry()
  sending.value = true; emit('busy', true)
  try {
    const context = await props.prepare()
    await run({ ...context, message, requestId: crypto.randomUUID() })
  } catch (error) {
    failure.value = error instanceof Error ? error.message : '草稿保存失败，请重试'
  } finally { sending.value = false; emit('busy', false) }
}
function retry() { if (pending.value && !sending.value) { unavailable.value = false; return run(pending.value) } }
function quickSend(message: string) { input.value = message; send() }
function sendMessage(message: string) { input.value = message; return send() }
watch(unavailable, value => emit('unavailable', value))
watch(() => [props.demandId, props.sessionId], () => {
  historyGeneration++; runGeneration++; controller?.abort()
  messages.value = []; latest.value = null; pending.value = null; input.value = ''; failure.value = ''
  restorePending(); loadHistory().catch(() => { failure.value = '历史对话暂未载入，请稍后重试' })
})
onMounted(() => { restorePending(); loadHistory().catch(() => { /* 首次进入无会话属正常 */ }) })
onBeforeUnmount(() => { historyGeneration++; runGeneration++; controller?.abort(); clearTimeout(thinkingTimer) })
defineExpose({ sendMessage })
</script>
<style scoped>
.chat-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.msg-box { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 12px 6px; scroll-behavior: smooth; }
.msg-row { display: flex; gap: 8px; align-items: flex-end; margin: 12px 0; }
.msg-row.user { flex-direction: row-reverse; }
.ava { width: 28px; height: 28px; border-radius: 9px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.ava.ag { background: #1f3a8a; color: #fff; }
.ava.me { background: #c7d2fe; color: #312e81; }
.msg-bubble { background: #fff; border: 1px solid #e5e9f2; border-radius: 12px; border-top-left-radius: 4px; padding: 10px 12px; font-size: 14px; line-height: 1.7; max-width: 82%; white-space: pre-wrap; overflow-wrap: anywhere; }
.msg-row.user .msg-bubble { color: #fff; background: #1f3a8a; border-color: #1f3a8a; border-radius: 12px; border-top-right-radius: 4px; }
.who { font-size: 12px; color: #999; margin-bottom: 3px; }
.user .who { color: #bfdbfe; }
.failure { background: #fff7ed; color: #9a3412; font-size: 12px; padding: 10px; line-height: 1.7; border-radius: 8px; }
.summary { margin: 8px 12px; padding: 10px; background: #eef3fb; border-radius: 8px; font-size: 12px; line-height: 1.6; }
.summary small { display: block; margin-top: 4px; color: #666; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 6px 12px; }
.chips button { border: 1px solid #a7b8d8; color: #1f3a8a; background: #fff; border-radius: 16px; padding: 7px 12px; font-size: 13px; min-height: 36px; }
.chips button.primary { background: #1f3a8a; color: #fff; border-color: #1f3a8a; }
.input-row { display: flex; align-items: flex-end; gap: 10px; padding: 8px 12px 4px; background: #fff; border-top: 1px solid #ebedf0; }
.input-row .van-field { border: 1px solid #eee; border-radius: 8px; }
.input-row .van-button { flex-shrink: 0; }
.tip { font-size: 11px; line-height: 1.6; color: #888; padding: 4px 14px max(6px, env(safe-area-inset-bottom)); background: #fff; }
.hint-banner { background: #fdf6ec; border-radius: 8px; padding: 8px 12px; margin: 8px 0; font-size: 12px; line-height: 1.7; color: #9a3412; display: flex; flex-direction: column; gap: 2px; }
.hint-banner.impact { background: #eef3fb; color: #1f3a8a; }
</style>
