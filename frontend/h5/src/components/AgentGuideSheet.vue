<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    :style="{ height: '85%' }"
    @update:show="emit('update:show', $event)"
    @open="onOpen"
  >
    <div class="guide-sheet">
      <!-- 头部 -->
      <div class="sheet-header">
        <span class="sheet-title">AI 提报助手</span>
        <span v-if="session" class="new-session" @click="onNewSession">新会话</span>
        <van-icon name="cross" size="18" color="#999" @click="emit('update:show', false)" />
      </div>

      <!-- 降级提示：大模型不可用时显示，主流程（手动填写提交）不受影响 -->
      <van-notice-bar
        v-if="unavailable"
        left-icon="warning-o"
        text="AI 服务暂不可用，请手动填写表单提交"
        class="unavailable-bar"
      />

      <!-- 消息区 -->
      <div ref="msgBoxRef" class="msg-box">
        <template v-if="!messages.length">
          <div class="empty-tip">随口说、粘贴一大段文字都行（可用输入法语音输入），我来帮你整理成规范表单</div>
          <!-- 快捷开场（消除冷启动障碍） -->
          <div v-if="!unavailable" class="chips">
            <span v-for="c in STARTERS" :key="c" class="chip" @click="onQuickSend(c)">{{ c }}</span>
          </div>
        </template>
        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role.toLowerCase()">
          <div class="msg-bubble">
            <span v-html="fmtContent(m.content)" />
            <span v-if="m.streaming" class="cursor">▍</span>
          </div>
        </div>
      </div>

      <!-- 要素完备度清单（P10：三态 rubric 可视化） -->
      <div v-if="elements.length" class="elements-box">
        <div class="elements-title">信息完备度（{{ okCount }}/{{ elements.length }}）</div>
        <div class="elements-list">
          <span v-for="e in elements" :key="e.key" class="element-item" :class="e.status.toLowerCase()" :title="e.note">
            <van-icon v-if="e.status === 'OK'" name="checked" />
            <van-icon v-else-if="e.status === 'VAGUE'" name="warning" />
            <van-icon v-else-if="e.status === 'SKIP'" name="minus" />
            <van-icon v-else name="circle" />
            {{ elementLabel(e.key) }}
          </span>
        </div>
        <div v-if="readyFlag" class="ready-tip">信息已齐，关闭后确认表单无误即可提交</div>
      </div>

      <!-- 结构化回填提示 -->
      <div v-if="lastStructured" class="fill-tip">
        <van-icon name="checked" color="#16a34a" />
        <span>
          已自动回填 {{ filledFields.join('、') }} 到表单，可直接编辑修改
          <template v-if="missingLabel">；还缺：{{ missingLabel }}</template>
        </span>
      </div>

      <!-- 快捷回复（选项类问题 / L3 逃生门） -->
      <div v-if="quickReplies.length && !sending" class="chips quick">
        <span v-for="q in quickReplies" :key="q" class="chip" @click="onQuickSend(q)">{{ q }}</span>
      </div>

      <!-- 输入区 -->
      <div class="input-row">
        <van-field
          v-model="input"
          type="textarea"
          rows="2"
          autosize
          :placeholder="unavailable ? 'AI 服务暂不可用' : '随口说或粘贴一大段'"
          :disabled="sending || unavailable"
          class="input-field"
        />
        <van-button
          type="primary"
          size="small"
          :loading="sending"
          :disabled="!input.trim() || unavailable"
          class="send-btn"
          @click="onSend"
        >发送</van-button>
      </div>
      <div class="tip">你已填写的内容不会被 AI 覆盖，最终以手动编辑为准</div>
    </div>
  </van-popup>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { showToast } from 'vant'
import {
  createAgentSession,
  listAgentSessions,
  agentSessionMessages,
  guideChatStream,
  AgentUnavailableError,
  type AgentSession,
  type ElementStatus,
  type GuideStructured
} from '@/api/agent'

interface Props {
  show: boolean
  /** 当前表单快照（用户手填优先，AI 不覆盖非空字段） */
  formContext: Record<string, unknown>
}

const props = defineProps<Props>()
const emit = defineEmits<{
  (e: 'update:show', v: boolean): void
  /** 结构化字段回填（父组件应用到表单，用户可再编辑） */
  (e: 'fill', fields: GuideStructured): void
}>()

interface UiMessage {
  role: 'USER' | 'ASSISTANT'
  content: string
  streaming?: boolean
}

/** 快捷开场短语（冷启动引导：高手整段/新手随口/语音都可） */
const STARTERS = ['我要做个报表', '系统不好用想优化', '要和其他系统对接']

const session = ref<AgentSession | null>(null)
const messages = ref<UiMessage[]>([])
const input = ref('')
const sending = ref(false)
const unavailable = ref(false)
const lastStructured = ref<GuideStructured | null>(null)
const lastMissing = ref<string[]>([])
const elements = ref<ElementStatus[]>([])
const quickReplies = ref<string[]>([])
const readyFlag = ref(false)
const msgBoxRef = ref<HTMLElement>()
let historyLoaded = false

const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  demandTypeCode: '类型',
  content: '描述',
  urgency: '紧急程度',
  expectDeliveryAt: '期望交付',
  ext: '扩展字段'
}

/** 要素键中文名（rubric 清单展示） */
const ELEMENT_LABELS: Record<string, string> = {
  title: '标题',
  content: '需求描述',
  techSubtype: '需求子类',
  businessScenario: '业务场景',
  acceptanceCriteria: '验收标准',
  valueImpact: '价值与影响'
}

const filledFields = computed(() =>
  Object.keys(lastStructured.value || {})
    .filter((k) => (lastStructured.value as Record<string, unknown>)[k] !== undefined)
    .map((k) => FIELD_LABELS[k] || k)
)

const missingLabel = computed(() =>
  lastMissing.value.length ? lastMissing.value.map((m) => FIELD_LABELS[m] || m).join('、') : ''
)

const okCount = computed(() => elements.value.filter((e) => e.status === 'OK').length)

function elementLabel(key: string): string {
  return ELEMENT_LABELS[key] || key
}

function fmtContent(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/\n/g, '<br>')
}

async function scrollToBottom() {
  await nextTick()
  msgBoxRef.value?.scrollTo({ top: msgBoxRef.value.scrollHeight })
}

async function ensureSession(firstMessage: string): Promise<AgentSession> {
  if (session.value && session.value.status === 'ACTIVE') {
    return session.value
  }
  session.value = await createAgentSession('SUBMIT_GUIDE', undefined, firstMessage)
  return session.value
}

/** 快捷短语/选项 chips：等同用户输入直接发送 */
function onQuickSend(text: string) {
  if (sending.value || unavailable.value) {
    return
  }
  input.value = text
  onSend()
}

async function onSend() {
  const text = input.value.trim()
  if (!text || sending.value) {
    return
  }
  sending.value = true
  try {
    const s = await ensureSession(text)
    messages.value.push({ role: 'USER', content: text })
    input.value = ''
    quickReplies.value = []
    const assistant: UiMessage = { role: 'ASSISTANT', content: '', streaming: true }
    messages.value.push(assistant)
    scrollToBottom()
    await guideChatStream(s.id, text, props.formContext, {
      onDelta: (delta) => {
        assistant.content += delta
        scrollToBottom()
      },
      onStructured: (payload) => {
        if (payload.structured && Object.keys(payload.structured).length) {
          lastStructured.value = payload.structured
          lastMissing.value = payload.missing || []
          emit('fill', payload.structured)
        }
        elements.value = payload.elements || []
        quickReplies.value = payload.quickReplies || []
        readyFlag.value = payload.ready && (payload.elements || []).every((e) => e.status === 'OK' || e.status === 'SKIP')
      }
    })
    assistant.streaming = false
  } catch (e) {
    // 流式中断：移除占位的空气泡
    messages.value = messages.value.filter((m) => !(m.role === 'ASSISTANT' && m.streaming && !m.content))
    if (e instanceof AgentUnavailableError && e.code === 1401) {
      unavailable.value = true
      showToast('AI 服务暂不可用，请手动填写表单')
    } else if (!(e instanceof Error && e.message === '登录已过期')) {
      showToast(e instanceof Error ? e.message : '发送失败')
    }
  } finally {
    sending.value = false
  }
}

function onNewSession() {
  session.value = null
  messages.value = []
  lastStructured.value = null
  lastMissing.value = []
  elements.value = []
  quickReplies.value = []
  readyFlag.value = false
  unavailable.value = false
}

/** 抽屉首次打开时加载历史会话 */
async function onOpen() {
  if (historyLoaded) {
    return
  }
  historyLoaded = true
  try {
    const sessions = await listAgentSessions('SUBMIT_GUIDE')
    const active = sessions.find((s) => s.status === 'ACTIVE')
    if (active) {
      session.value = active
      const history = await agentSessionMessages(active.id)
      messages.value = history
        .filter((m) => m.role === 'USER' || m.role === 'ASSISTANT')
        .map((m) => ({ role: m.role as 'USER' | 'ASSISTANT', content: m.content }))
      scrollToBottom()
    }
  } catch {
    // 历史会话加载失败不影响提报
  }
}
</script>

<style scoped>
.guide-sheet {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 12px 14px 10px;
  box-sizing: border-box;
}

.sheet-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 8px;
}

.sheet-title {
  flex: 1;
  font-size: 16px;
  font-weight: 600;
}

.new-session {
  font-size: 13px;
  color: #1F3A8A;
}

.unavailable-bar {
  border-radius: 8px;
  margin-bottom: 8px;
}

.msg-box {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 2px;
}

.empty-tip {
  color: #999;
  font-size: 13px;
  text-align: center;
  padding: 24px 16px 14px;
  line-height: 1.7;
}

.msg-row {
  display: flex;
  margin: 8px 0;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-bubble {
  max-width: 88%;
  padding: 8px 10px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
  background: #f2f4f8;
  word-break: break-word;
}

.msg-row.user .msg-bubble {
  background: #1F3A8A;
  color: #fff;
}

.cursor {
  animation: blink 0.8s infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

/* 要素完备度清单（三态） */
.elements-box {
  border: 1px solid #ebedf0;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 6px 0;
  font-size: 12px;
}

.elements-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: #323233;
}

.elements-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.element-item {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: #969799;
}

.element-item.ok {
  color: #07c160;
}

.element-item.vague {
  color: #ff976a;
}

.element-item.skip {
  color: #c8c9cc;
}

.ready-tip {
  margin-top: 6px;
  color: #07c160;
}

.fill-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: #f0f9eb;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  margin: 6px 0;
  color: #323233;
}

/* 快捷开场 / 快捷回复 chips */
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 8px 10px;
  justify-content: center;
}

.chips.quick {
  justify-content: flex-start;
  padding: 0 0 8px;
}

.chip {
  border: 1px solid #7c9ad4;
  color: #1F3A8A;
  border-radius: 14px;
  padding: 5px 12px;
  font-size: 12px;
  user-select: none;
}

.chip:active {
  background: #eef3fb;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding-top: 6px;
}

.input-field {
  flex: 1;
  border: 1px solid #ebedf0;
  border-radius: 8px;
  padding: 6px 10px;
}

.send-btn {
  flex-shrink: 0;
  height: 36px;
  border-radius: 8px;
}

.tip {
  color: #969799;
  font-size: 11px;
  margin-top: 6px;
}
</style>
