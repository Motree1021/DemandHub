<template>
  <van-popup :show="show" position="bottom" round :style="{ height: '86%' }" @update:show="emit('update:show', $event)" @open="onOpen">
    <div class="guide-sheet">
      <div class="sheet-header"><strong>AI 提报助手</strong><van-icon name="cross" size="20" @click="emit('update:show', false)" /></div>
      <van-notice-bar v-if="unavailable" text="AI 暂不可用，仍可关闭助手后手动填写和提交" left-icon="warning-o" />
      <div ref="msgBox" class="msg-box">
        <p v-if="!messages.length && !sending" class="empty-tip">随口说、粘一大段、输入法语音输入都行。AI 会整理当前草稿，并一次追问一个缺口。</p>
        <div v-for="message in messages" :key="message.id" class="msg-row" :class="message.role.toLowerCase()"><div class="msg-bubble">{{ message.content }}</div></div>
        <template v-if="sending">
          <div class="msg-row user"><div class="msg-bubble">{{ pending?.message }}</div></div>
          <div class="msg-row assistant"><div class="msg-bubble">{{ partialReply || (thinking ? '正在思考和整理…' : '正在处理…') }}</div></div>
        </template>
        <p v-if="failure" class="failure">{{ failure }}<br>原输入与请求已保留。可重试恢复已保存结果。</p>
      </div>
      <div v-if="latest" class="summary">
        <span>{{ latest.canSubmit ? '必填与格式已满足，可确认表单后提交' : '请补充必填或修正格式后提交' }}</span>
        <small v-if="!latest.qualityComplete">信息仍有质量缺口，跳过的内容会标记为待后续补充。</small>
        <small v-if="latest.guidanceComplete && !latest.qualityComplete">本轮引导已结束，可继续手动完善。</small>
      </div>
      <div v-if="latest?.quickReplies.length && !sending" class="chips"><button v-for="reply in latest.quickReplies" :key="reply" @click="quickSend(reply)">{{ reply }}</button></div>
      <van-button v-if="pending && !sending" size="small" plain type="primary" @click="retry">重试上一条</van-button>
      <div class="input-row">
        <van-field v-model="input" type="textarea" rows="2" autosize :disabled="sending" placeholder="随口说或粘贴一大段" />
        <van-button type="primary" :loading="sending" :disabled="!input.trim() || unavailable" @click="send">发送</van-button>
      </div>
      <small class="tip">发送前会保存表单；你明确手改的内容由服务端保护。最终提交内容以表单为准。</small>
    </div>
  </van-popup>
</template>
<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { agentSessionMessages, guideChatStream, StreamError, type GuidePayload, type GuideRequest } from '@/api/agent'
import type { AgentMessage } from '@/api/demand'
import { canApplyRevision } from '@/utils/form'
const props = defineProps<{
  show: boolean; demandId: number | null; sessionId: number | null; revision: number
  prepare: () => Promise<{ demandId: number; sessionId: number; revision: number }>
}>()
const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'busy', value: boolean): void
  (event: 'complete', value: GuidePayload): void
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
async function scroll() { await nextTick(); msgBox.value?.scrollTo?.({ top: msgBox.value.scrollHeight, behavior: 'smooth' }) }
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
async function onOpen() {
  failure.value = ''; unavailable.value = false; latest.value = null
  try {
    const saved = sessionStorage.getItem(pendingKey())
    if (saved) {
      const request = JSON.parse(saved) as GuideRequest
      if (request.demandId === props.demandId && request.sessionId === props.sessionId) { pending.value = request; input.value = request.message }
    }
    await loadHistory()
  } catch { failure.value = '历史对话暂未载入，请稍后重新打开' }
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
watch(() => props.show, value => { if (!value) controller?.abort() })
watch(() => [props.demandId, props.sessionId], () => { historyGeneration++; runGeneration++; controller?.abort(); messages.value = []; latest.value = null; pending.value = null; input.value = ''; failure.value = '' })
onBeforeUnmount(() => { historyGeneration++; runGeneration++; controller?.abort(); clearTimeout(thinkingTimer) })
</script>
<style scoped>
.guide-sheet { display: flex; flex-direction: column; height: 100%; padding: 16px 14px max(14px, env(safe-area-inset-bottom)); gap: 10px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; }.msg-box { flex: 1; min-height: 0; overflow-y: auto; }.empty-tip { font-size: 13px; color: #777; line-height: 1.8; padding: 20px 12px; text-align: center; }.msg-row { display: flex; margin: 10px 0; }.msg-row.user { justify-content: flex-end; }.msg-bubble { background: #eef1f6; border-radius: 10px; padding: 10px 12px; font-size: 14px; line-height: 1.7; max-width: 90%; white-space: pre-wrap; overflow-wrap: anywhere; }.user .msg-bubble { color: #fff; background: #1f3a8a; }.failure { background: #fff7ed; color: #9a3412; font-size: 12px; padding: 10px; line-height: 1.7; }.summary { padding: 10px; background: #eef3fb; font-size: 12px; line-height: 1.6; }.summary small { display: block; margin-top: 4px; color: #666; }.chips { display: flex; flex-wrap: wrap; gap: 8px; }.chips button { border: 1px solid #a7b8d8; color: #1f3a8a; background: #fff; border-radius: 16px; padding: 6px 10px; }.input-row { display: flex; align-items: flex-end; gap: 10px; }.input-row .van-field { border: 1px solid #eee; border-radius: 8px; }.input-row .van-button { flex-shrink: 0; }.tip { font-size: 11px; line-height: 1.6; color: #888; }
</style>
