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
      <el-empty v-if="!messages.length" description="用一句话描述你的需求，我来帮你整理成规范表单" :image-size="60" />
      <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role.toLowerCase()">
        <div class="msg-bubble">
          <span v-html="fmtContent(m.content)" />
          <span v-if="m.streaming" class="cursor">▍</span>
        </div>
      </div>
    </div>

    <!-- 结构化回填提示 -->
    <div v-if="lastStructured" class="fill-tip">
      <el-icon color="#16a34a"><CircleCheckFilled /></el-icon>
      <span>
        已自动回填 {{ filledFields.join('、') }} 到左侧表单，可直接编辑修改
        <template v-if="missingLabel">；还缺：{{ missingLabel }}</template>
      </span>
    </div>

    <!-- 输入区 -->
    <div class="input-row">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        resize="none"
        :placeholder="unavailable ? 'AI 服务暂不可用' : '如：我想要个数据报表'"
        :disabled="sending || unavailable"
        @keydown.enter.exact.prevent="onSend"
      />
      <el-button type="primary" :loading="sending" :disabled="!input.trim() || unavailable" @click="onSend">发送</el-button>
    </div>
    <div class="muted tip">Enter 发送；AI 抽取的字段会自动回填，最终以你手动编辑为准</div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createAgentSession,
  listAgentSessions,
  agentSessionMessages,
  guideChatStream,
  AgentUnavailableError,
  type AgentSession,
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

const session = ref<AgentSession | null>(null)
const messages = ref<UiMessage[]>([])
const input = ref('')
const sending = ref(false)
const unavailable = ref(false)
const lastStructured = ref<GuideStructured | null>(null)
const lastMissing = ref<string[]>([])
const msgBoxRef = ref<HTMLElement>()

const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  demandTypeCode: '类型',
  content: '描述',
  urgency: '紧急程度',
  expectDeliveryAt: '期望交付',
  ext: '扩展字段'
}

const filledFields = computed(() =>
  Object.keys(lastStructured.value || {})
    .filter((k) => (lastStructured.value as Record<string, unknown>)[k] !== undefined)
    .map((k) => FIELD_LABELS[k] || k)
)

const missingLabel = computed(() =>
  lastMissing.value.length ? lastMissing.value.map((m) => FIELD_LABELS[m] || m).join('、') : ''
)

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
