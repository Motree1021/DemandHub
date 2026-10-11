<template>
  <div class="chat-panel">
    <van-notice-bar v-if="unavailable" text="AI 暂不可用，请稍后再试" left-icon="warning-o" wrapable />
    <div ref="msgBox" class="msg-box">
      <slot v-if="!messages.length && !sending" name="welcome" />
      <div v-for="message in messages" :key="message.id" class="msg-row" :class="message.role.toLowerCase()">
        <div class="ava" :class="message.role === 'USER' ? 'me' : 'ag'">{{ message.role === 'USER' ? '我' : 'AI' }}</div>
        <div v-if="manualChanges.get(message.id)" class="msg-bubble change-bubble">
          <div v-for="(change, index) in manualChanges.get(message.id)!.changes" :key="index" class="change-item">
            <p class="change-head">{{ change.action === 'fill' ? `你已手动填写了「${change.label}」` : change.action === 'clear' ? `你已手动清空了「${change.label}」` : `你已手动更新了「${change.label}」` }}</p>
            <div v-if="change.action !== 'clear'" class="change-line">
              <span class="change-tag" :class="change.action === 'update' ? 'new' : 'plain'">{{ change.action === 'update' ? '改为' : '内容' }}</span>
              <span class="change-value new">{{ change.new }}</span>
            </div>
            <div v-if="change.action === 'update'" class="change-line">
              <span class="change-tag old">原来</span>
              <span class="change-value old">{{ change.old }}</span>
            </div>
          </div>
        </div>
        <div v-else-if="attachmentOf(message)?.kind === 'attachment'" class="msg-bubble attach-bubble" :class="{ mine: message.role === 'USER' }" @click="openAttachment(message)">
          <img v-if="attachmentOf(message)!.fileKind === 'IMAGE' && thumbs.get(attachmentOf(message)!.attachmentId)" class="attach-thumb" :src="thumbs.get(attachmentOf(message)!.attachmentId)" alt="">
          <div v-else-if="attachmentOf(message)!.fileKind === 'IMAGE'" class="attach-pending">图片加载中…</div>
          <div class="attach-line">
            <van-icon :name="attachmentOf(message)!.fileKind === 'IMAGE' ? 'photo-o' : 'description'" class="attach-icon" />
            <span class="attach-meta">
              <strong>{{ attachmentOf(message)!.fileName }}</strong>
              <small v-if="attachmentOf(message)!.size">{{ fmtSize(attachmentOf(message)!.size!) }} · 点击查看</small>
              <small v-else>点击查看</small>
            </span>
          </div>
        </div>
        <div v-else class="msg-bubble">{{ message.content }}</div>
      </div>
      <template v-if="sending">
        <div class="msg-row user"><div class="ava me">我</div><div class="msg-bubble">{{ pending?.message }}</div></div>
        <div class="msg-row assistant"><div class="ava ag">AI</div><div class="msg-bubble">{{ partialReply || (thinking ? '正在思考和整理…' : '正在处理…') }}</div></div>
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
    </div>
    <div v-if="latest?.canSubmit && !sending" class="chips">
      <button class="primary" @click="emit('submit')">确认提交</button>
      <button @click="emit('save-draft')">先保存草稿，稍后再提交</button>
    </div>
    <div v-if="latest?.quickReplies.length && !sending" class="chips"><button v-for="reply in latest.quickReplies" :key="reply" @click="quickSend(reply)">{{ reply }}</button></div>
    <van-button v-if="pending && !sending" size="small" plain type="primary" @click="retry">重试上一条</van-button>
    <div class="input-row">
      <button class="attach-btn" :disabled="sending || uploading" aria-label="上传附件" @click="attachVisible = true">＋</button>
      <van-field v-model="input" type="textarea" rows="2" autosize :disabled="sending" placeholder="继续说，或粘贴大段需求…" />
      <van-button type="primary" :loading="sending" :disabled="!input.trim() || unavailable" @click="send">发送</van-button>
    </div>
    <van-action-sheet v-model:show="attachVisible" :actions="attachActions" cancel-text="取消" close-on-click-action
      :description="`AI 暂不支持识别附件内容，附件仅作为需求材料随需求一并提交给受理方；单文件不超过 10MB，最多 ${ATTACHMENT_COUNT_LIMIT} 个`"
      @select="onAttachSelect" />
    <input ref="imageInput" type="file" :accept="ATTACHMENT_ACCEPT.image" hidden @change="onFileChosen($event)">
    <input ref="docInput" type="file" :accept="ATTACHMENT_ACCEPT.doc" hidden @change="onFileChosen($event)">
    <span v-if="uploading" class="uploading-hint">附件上传中…</span>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { showImagePreview, showToast } from 'vant'
import { agentSessionMessages, guideChatStream, StreamError, type GuidePayload, type GuideRequest } from '@/api/agent'
import {
  ATTACHMENT_ACCEPT, ATTACHMENT_COUNT_LIMIT, ATTACHMENT_SIZE_LIMIT, fmtSize, isReplayablePayload,
  parseAttachmentPayload, parseManualChange, uploadAttachment, fetchAttachmentThumb, downloadAttachment,
  type AgentMessage, type AttachmentPayload, type DemandForm, type ElementStatus, type ManualChangePayload, type Standard, type StandardField,
} from '@/api/demand'
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
// 手工改要素播报：按消息 id 解析结构化 payload，命中则渲染改动手卡片而非纯文本
const manualChanges = computed(() => {
  const map = new Map<number, ManualChangePayload>()
  for (const message of messages.value) {
    const payload = parseManualChange(message.structuredPayload)
    if (payload) map.set(message.id, payload)
  }
  return map
})
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
  // 质量清单回放只认对话结果消息，手改播报/附件回执卡片不参与回放
  const last = [...messages.value].reverse().find(message => message.role === 'ASSISTANT' && isReplayablePayload(message.structuredPayload))
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
  // 发送即刻上提：用户消息与“正在思考”一出现就保证可见，不等首个流式事件
  scroll()
  controller = new AbortController()
  thinkingTimer = setTimeout(() => { thinking.value = true }, 5000)
  try {
    const payload = await guideChatStream(request, { onDelta: delta => { partialReply.value += delta; scroll() }, onProcessing: () => scroll() }, controller.signal)
    if (generation !== runGeneration || props.demandId !== request.demandId || props.sessionId !== request.sessionId) return
    latest.value = payload
    emit('complete', payload)
    scroll()
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
watch(unavailable, value => emit('unavailable', value))
// 消息增多自动上提：始终保持最新一条可见（历史载入、逐字输出、卡片落位另有点位调用 scroll）
watch(() => messages.value.length, () => scroll())

// ---- 附件上传（阶段一）：＋面板选择来源，本机文件直传；企微/微信选择待宿主桥接 ----
const attachVisible = ref(false)
const uploading = ref(false)
const imageInput = ref<HTMLInputElement>()
const docInput = ref<HTMLInputElement>()
const thumbs = ref(new Map<number, string>())
const attachActions = [
  { name: '拍照或选择图片', value: 'image' },
  { name: '上传文档（md / pdf / word / ppt）', value: 'doc' },
  { name: '从微信/企微选择文件', subname: '即将支持' },
]
function attachmentOf(message: AgentMessage): AttachmentPayload | null {
  return parseAttachmentPayload(message.structuredPayload)
}
function onAttachSelect(action: { value?: string }) {
  if (action.value === 'image') imageInput.value?.click()
  else if (action.value === 'doc') docInput.value?.click()
  else pickFromWeChat()
}
/** 企微/微信选文件桥接（分期预留，2026-10-11 拍板）：网页够不到微信聊天文件/微文档，
 *  需宿主小程序提供 wx.chooseMessageFile 桥并把选中文件回传 H5，回传后复用 uploadAttachment 走同一上传链路。
 *  对接要求见 docs/DemandHub对创金零售渠道_对接要求说明书_v2.0.md 附件桥接章节。 */
function pickFromWeChat() {
  showToast('即将支持：需小程序宿主配合开通，开通后可直接从微信/企微选文件')
}
async function onFileChosen(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  target.value = ''
  if (!file || sending.value || uploading.value) return
  if (file.size > ATTACHMENT_SIZE_LIMIT) { showToast('文件超过 10MB 上限'); return }
  uploading.value = true; emit('busy', true)
  try {
    const context = await props.prepare()
    await uploadAttachment(context.demandId, file)
    await loadHistory()
  } catch { /* 失败原因已由请求层 toast；本地上传不消耗 AI 额度，直接重试即可 */ }
  finally { uploading.value = false; emit('busy', false); scroll() }
}
function openAttachment(message: AgentMessage) {
  const payload = attachmentOf(message)
  if (!payload || !props.demandId) return
  if (payload.fileKind === 'IMAGE') {
    const url = thumbs.value.get(payload.attachmentId)
    if (url) showImagePreview({ images: [url], closeable: true })
  } else {
    downloadAttachment(props.demandId, payload.attachmentId, payload.fileName).catch(() => { /* 错误已展示 */ })
  }
}
// 图片附件缩略图：消息载入后按附件 id 拉鉴权 blob，成功缓存 objectURL；会话切换与卸载时释放
watch(messages, () => {
  const seen = new Set<number>()
  for (const message of messages.value) {
    const payload = attachmentOf(message)
    if (!payload || payload.fileKind !== 'IMAGE' || seen.has(payload.attachmentId)) continue
    seen.add(payload.attachmentId)
    if (thumbs.value.has(payload.attachmentId) || !props.demandId) continue
    fetchAttachmentThumb(props.demandId, payload.attachmentId).then(url => {
      thumbs.value.set(payload.attachmentId, url)
      thumbs.value = new Map(thumbs.value)
    }).catch(() => { /* 缩略图加载失败回落文件名卡片，点击仍可重试 */ })
  }
}, { deep: true })
function releaseThumbs() {
  thumbs.value.forEach(url => URL.revokeObjectURL(url))
  thumbs.value = new Map()
}
watch(() => [props.demandId, props.sessionId], () => {
  releaseThumbs()
  historyGeneration++; runGeneration++; controller?.abort()
  messages.value = []; latest.value = null; pending.value = null; input.value = ''; failure.value = ''
  restorePending(); loadHistory().catch(() => { failure.value = '历史对话暂未载入，请稍后重试' })
})
onMounted(() => { restorePending(); loadHistory().catch(() => { /* 首次进入无会话属正常 */ }) })
onBeforeUnmount(() => { historyGeneration++; runGeneration++; controller?.abort(); clearTimeout(thinkingTimer); releaseThumbs() })
defineExpose({ scrollToBottom: scroll, refreshHistory: loadHistory })
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
/* 手改播报卡片：标题点明改动，新值品牌蓝突出，旧值灰色弱化 */
.change-bubble { background: #f7f9ff; border-color: #dbe4f3; min-width: 200px; }
.change-item + .change-item { margin-top: 8px; padding-top: 8px; border-top: 1px dashed #e0e6f0; }
.change-head { margin: 0 0 4px; font-size: 13px; font-weight: 600; color: #1f3a8a; }
.change-line { display: flex; align-items: flex-start; gap: 6px; margin-top: 4px; font-size: 13px; line-height: 1.6; }
.change-tag { flex-shrink: 0; font-size: 11px; line-height: 20px; padding: 0 7px; border-radius: 4px; background: #e8edf5; color: #5b6472; }
.change-tag.new { background: #1f3a8a; color: #fff; }
.change-value { overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.change-value.new { color: #1f3a8a; font-weight: 500; }
.change-value.old { color: #94a3b8; }
.failure { background: #fff7ed; color: #9a3412; font-size: 12px; padding: 10px; line-height: 1.7; border-radius: 8px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 6px 12px; }
.chips button { border: 1px solid #a7b8d8; color: #1f3a8a; background: #fff; border-radius: 16px; padding: 7px 12px; font-size: 13px; min-height: 36px; }
.chips button.primary { background: #1f3a8a; color: #fff; border-color: #1f3a8a; }
.input-row { display: flex; align-items: flex-end; gap: 10px; padding: 8px 12px 4px; background: #fff; border-top: 1px solid #ebedf0; }
.input-row .van-field { border: 1px solid #eee; border-radius: 8px; }
.input-row .van-button { flex-shrink: 0; }
.attach-btn { width: 36px; height: 36px; flex-shrink: 0; margin-bottom: 1px; border: 1px solid #dbe4f3; border-radius: 8px; background: #f7f9ff; color: #1f3a8a; font-size: 20px; line-height: 1; display: flex; align-items: center; justify-content: center; }
.attach-btn:disabled { color: #b4bdcc; background: #f3f4f7; }
.uploading-hint { padding: 0 14px 8px; font-size: 12px; color: #5b6472; }
/* 附件消息卡片：图片缩略图置顶，文件行置底；用户侧卡片品牌蓝底白字与普通用户气泡一致 */
.attach-bubble { min-width: 180px; max-width: 82%; padding: 8px; cursor: pointer; }
.attach-bubble.mine { background: #1f3a8a; border-color: #1f3a8a; color: #fff; }
.attach-thumb { display: block; width: 100%; max-height: 180px; object-fit: cover; border-radius: 8px; margin-bottom: 6px; }
.attach-pending { font-size: 12px; color: #94a3b8; padding: 24px 0; text-align: center; }
.attach-line { display: flex; align-items: center; gap: 8px; }
.attach-icon { font-size: 20px; }
.attach-meta { display: flex; flex-direction: column; overflow: hidden; }
.attach-meta strong { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attach-meta small { font-size: 11px; color: #94a3b8; }
.attach-bubble.mine .attach-meta small { color: #c7d2fe; }
.hint-banner { background: #fdf6ec; border-radius: 8px; padding: 8px 12px; margin: 8px 0; font-size: 12px; line-height: 1.7; color: #9a3412; display: flex; flex-direction: column; gap: 2px; }
.hint-banner.impact { background: #eef3fb; color: #1f3a8a; }
</style>
