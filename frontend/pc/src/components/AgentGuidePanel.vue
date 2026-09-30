<template>
  <el-card shadow="never" class="agent-panel">
    <template #header>
      <div class="panel-header">
        <span>
          AI 提报助手
          <el-tag size="small" type="success" effect="plain" style="margin-left: 6px">M9</el-tag>
        </span>
        <el-button v-if="session" text type="primary" size="small" @click="onNewSession">新会话</el-button>
      </div>
    </template>

    <!-- 降级提示：大模型不可用时显示，主流程（手动填写提交）不受影响 -->
    <el-alert
      v-if="unavailable"
      type="warning"
      :closable="false"
      title="AI 服务暂不可用，请手动填写表单提交"
      style="margin-bottom: 10px"
    />

    <!-- 消息区 -->
    <div ref="msgBoxRef" class="msg-box">
      <template v-if="!messages.length">
        <el-empty description="随口说、粘贴一大段文字都行，我来帮你整理成规范表单" :image-size="60" />
        <!-- 快捷开场（消除冷启动障碍） -->
        <div v-if="!unavailable" class="starter-chips">
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
          <el-icon v-if="e.status === 'OK'"><CircleCheckFilled /></el-icon>
          <el-icon v-else-if="e.status === 'VAGUE'"><WarningFilled /></el-icon>
          <el-icon v-else-if="e.status === 'SKIP'"><RemoveFilled /></el-icon>
          <el-icon v-else><QuestionFilled /></el-icon>
          {{ elementLabel(e.key) }}
        </span>
      </div>
      <div v-if="readyFlag" class="ready-tip">信息已齐，确认表单无误后即可提交</div>
    </div>

    <!-- 结构化回填提示 -->
    <div v-if="lastStructured" class="fill-tip">
      <el-icon color="#16a34a"><CircleCheckFilled /></el-icon>
      <span>
        已自动回填 {{ filledFields.join('、') }} 到左侧表单，可直接编辑修改
        <template v-if="missingLabel">；还缺：{{ missingLabel }}</template>
      </span>
    </div>

    <!-- 快捷回复（选项类问题 / L3 逃生门） -->
    <div v-if="quickReplies.length && !sending" class="quick-chips">
      <span v-for="q in quickReplies" :key="q" class="chip" @click="onQuickSend(q)">{{ q }}</span>
    </div>

    <!-- 输入区 -->
    <div class="input-row">
      <el-input
        v-model="input"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        resize="none"
        :placeholder="unavailable ? 'AI 服务暂不可用' : '随口说或粘贴一大段；手机上可用输入法语音输入'"
        :disabled="sending || unavailable"
        @keydown.enter.exact.prevent="onSend"
      />
      <el-button type="primary" :loading="sending" :disabled="!input.trim() || unavailable" @click="onSend">发送</el-button>
    </div>
    <div class="muted tip">Enter 发送，Shift+Enter 换行；你已填写的内容不会被 AI 覆盖，最终以手动编辑为准</div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled, QuestionFilled, RemoveFilled, WarningFilled } from '@element-plus/icons-vue'
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
  /** 当前表单快照（用户手填优先，AI 不覆盖非空字段） */
  formContext: Record<string, unknown>
}

const props = defineProps<Props>()
const emit = defineEmits<{
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
      ElMessage.warning('AI 服务暂不可用，请手动填写表单')
    } else if (!(e instanceof Error && e.message === '登录已过期')) {
      ElMessage.error(e instanceof Error ? e.message : '发送失败')
    }
  } finally {
    sending.value = false
  }
}

async function onNewSession() {
  session.value = null
  messages.value = []
  lastStructured.value = null
  lastMissing.value = []
  elements.value = []
  quickReplies.value = []
  readyFlag.value = false
  unavailable.value = false
}

onMounted(async () => {
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
})
</script>

<style scoped>
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.msg-box {
  height: 300px;
  overflow-y: auto;
  padding: 4px 2px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 10px;
}

.msg-row {
  display: flex;
  margin: 8px;
}

.msg-row.user {
  justify-content: flex-end;
}

.msg-bubble {
  max-width: 88%;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  background: var(--el-fill-color-light);
  word-break: break-word;
}

.msg-row.user .msg-bubble {
  background: var(--el-color-primary);
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

.fill-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: #f0f9eb;
  border: 1px solid #c2e7b0;
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  margin-bottom: 10px;
}

/* 要素完备度清单（三态） */
.elements-box {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 10px;
  font-size: 12px;
}

.elements-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: var(--el-text-color-regular);
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
  color: var(--el-text-color-secondary);
}

.element-item.ok {
  color: var(--el-color-success);
}

.element-item.vague {
  color: var(--el-color-warning);
}

.element-item.skip {
  color: var(--el-text-color-disabled);
}

.ready-tip {
  margin-top: 6px;
  color: var(--el-color-success);
}

/* 快捷开场 / 快捷回复 chips */
.starter-chips,
.quick-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 8px 10px;
}

.quick-chips {
  padding: 0 0 8px;
}

.chip {
  border: 1px solid var(--el-color-primary-light-5);
  color: var(--el-color-primary);
  border-radius: 14px;
  padding: 3px 12px;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}

.chip:hover {
  background: var(--el-color-primary-light-9);
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.input-row .el-button {
  flex-shrink: 0;
}

.muted.tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 6px;
}
</style>
