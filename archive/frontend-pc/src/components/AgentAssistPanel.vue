<template>
  <el-card shadow="never" class="mb16">
    <template #header>
      <div class="card-header">
        <span>
          AI 处理助手
          <el-tag size="small" type="success" effect="plain" style="margin-left: 6px">M9</el-tag>
        </span>
        <div v-if="session">
          <el-button size="small" text type="primary" :loading="generating === 'QUESTIONS'" @click="onGenerate('QUESTIONS')">
            调研问题清单
          </el-button>
          <el-button size="small" text type="primary" :loading="generating === 'SOLUTION'" @click="onGenerate('SOLUTION')">
            方案初稿
          </el-button>
        </div>
      </div>
    </template>

    <el-alert
      v-if="unavailable"
      type="warning"
      :closable="false"
      title="AI 服务暂不可用，可正常人工处理需求"
      style="margin-bottom: 8px"
    />

    <template v-if="!session">
      <div class="start-row">
        <span class="muted">AI 辅助生成调研问题与方案初稿，确认后入库</span>
        <el-button size="small" type="primary" plain :disabled="unavailable" @click="onStart">开启辅助</el-button>
      </div>
    </template>

    <template v-else>
      <el-empty v-if="!drafts.length" description="暂无草稿，点击右上角生成" :image-size="50" />
      <div v-for="d in drafts" :key="d.id" class="draft-item">
        <div class="draft-head">
          <el-tag size="small" :type="d.draftType === 'SOLUTION' ? 'primary' : 'warning'" effect="plain">
            {{ d.draftType === 'SOLUTION' ? '方案初稿' : '调研问题' }}
          </el-tag>
          <el-tag v-if="d.status === 'PENDING'" size="small" type="danger" effect="plain">AI 生成需人工确认</el-tag>
          <el-tag v-else-if="d.status === 'CONFIRMED'" size="small" type="success" effect="plain">已入库</el-tag>
          <el-tag v-else size="small" type="info" effect="plain">已废弃</el-tag>
          <span class="muted time">{{ fmtTime(d.createdAt) }}</span>
        </div>

        <!-- 问题清单 -->
        <ul v-if="d.draftType === 'QUESTIONS'" class="question-list">
          <li v-for="(q, i) in parseQuestions(d.content)" :key="i">{{ q }}</li>
        </ul>

        <!-- 方案初稿 -->
        <template v-else>
          <div class="sol-preview">
            <div class="sol-block">
              <div class="sol-label">需求理解</div>
              <pre>{{ parseSolution(d.content).specContent }}</pre>
            </div>
            <div class="sol-block">
              <div class="sol-label">方案内容</div>
              <pre>{{ parseSolution(d.content).solutionContent }}</pre>
            </div>
          </div>
        </template>

        <div v-if="d.status === 'PENDING'" class="draft-actions">
          <el-button
            v-if="d.draftType === 'SOLUTION'"
            size="small"
            type="primary"
            :disabled="!canConfirm"
            @click="openConfirm(d)"
          >
            确认入库
          </el-button>
          <el-button size="small" text type="danger" @click="onDiscard(d)">废弃</el-button>
        </div>
        <div v-if="d.status === 'CONFIRMED' && d.targetSolutionId" class="muted" style="margin-top: 4px">
          已写入方案 V 版本（#{{ d.targetSolutionId }}），见左侧「方案与评审」
        </div>
      </div>
    </template>

    <!-- 确认入库对话框：可编辑后再提交 -->
    <el-dialog v-model="confirmDlg" title="确认方案入库（可编辑）" width="720px" append-to-body>
      <el-alert type="warning" :closable="false" title="确认后将写入方案表（DRAFT 新版本），进入既有评审流程" style="margin-bottom: 10px" />
      <el-form label-width="90px">
        <el-form-item label="需求理解">
          <el-input v-model="confirmForm.specContent" type="textarea" :rows="5" />
        </el-form-item>
        <el-form-item label="方案内容">
          <el-input v-model="confirmForm.solutionContent" type="textarea" :rows="9" />
        </el-form-item>
        <el-form-item label="计划交付">
          <el-date-picker v-model="confirmForm.planDeliveryAt" type="date" value-format="YYYY-MM-DDT00:00:00" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="confirmDlg = false">取消</el-button>
        <el-button type="primary" :loading="confirming" :disabled="!confirmForm.solutionContent.trim()" @click="onConfirm">
          确认入库
        </el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createAgentSession,
  listAgentSessions,
  assistQuestions,
  assistSolution,
  assistDrafts,
  confirmSolutionDraft,
  discardDraft,
  type AgentDraft,
  type AgentSession
} from '@/api/agent'
import { fmtTime } from '@/utils/format'

interface Props {
  demandId: number
  /** 需求状态：仅 ANALYZING 允许方案确认入库（与后端一致） */
  demandStatus: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  /** 方案确认入库后通知父组件刷新方案列表 */
  (e: 'confirmed'): void
}>()

const session = ref<AgentSession | null>(null)
const drafts = ref<AgentDraft[]>([])
const generating = ref<'' | 'QUESTIONS' | 'SOLUTION'>('')
const unavailable = ref(false)

const confirmDlg = ref(false)
const confirming = ref(false)
const confirmingDraftId = ref<number | null>(null)
const confirmForm = reactive({ specContent: '', solutionContent: '', planDeliveryAt: undefined as string | undefined })

const canConfirm = computed(() => props.demandStatus === 'ANALYZING')

function isUnavailableError(e: unknown): boolean {
  return e instanceof Error && (e.message.includes('AI 服务暂不可用') || e.message.includes('1401'))
}

async function onStart() {
  try {
    session.value = await createAgentSession('HANDLE_ASSIST', props.demandId)
  } catch {
    /* 拦截器已提示 */
  }
}

async function onGenerate(type: 'QUESTIONS' | 'SOLUTION') {
  if (!session.value) {
    return
  }
  generating.value = type
  try {
    if (type === 'QUESTIONS') {
      await assistQuestions(session.value.id)
    } else {
      await assistSolution(session.value.id)
    }
    ElMessage.success('已生成，请人工核对后确认入库')
    await loadDrafts()
  } catch (e) {
    if (isUnavailableError(e)) {
      unavailable.value = true
    }
  } finally {
    generating.value = ''
  }
}

async function loadDrafts() {
  try {
    drafts.value = await assistDrafts(props.demandId)
  } catch {
    /* 角色不足等场景静默 */
  }
}

function parseQuestions(content: string): string[] {
  try {
    return JSON.parse(content) as string[]
  } catch {
    return [content]
  }
}

function parseSolution(content: string): { specContent: string; solutionContent: string } {
  try {
    const obj = JSON.parse(content) as { specContent?: string; solutionContent?: string }
    return { specContent: obj.specContent || '', solutionContent: obj.solutionContent || '' }
  } catch {
    return { specContent: '', solutionContent: content }
  }
}

function openConfirm(d: AgentDraft) {
  const parsed = parseSolution(d.content)
  confirmingDraftId.value = d.id
  confirmForm.specContent = parsed.specContent
  confirmForm.solutionContent = parsed.solutionContent
  confirmForm.planDeliveryAt = undefined
  confirmDlg.value = true
}

async function onConfirm() {
  if (!confirmingDraftId.value) {
    return
  }
  confirming.value = true
  try {
    await confirmSolutionDraft(confirmingDraftId.value, {
      specContent: confirmForm.specContent,
      solutionContent: confirmForm.solutionContent,
      planDeliveryAt: confirmForm.planDeliveryAt
    })
    ElMessage.success('方案已入库（DRAFT），可在「方案与评审」中继续操作')
    confirmDlg.value = false
    await loadDrafts()
    emit('confirmed')
  } catch {
    /* 拦截器已提示 */
  } finally {
    confirming.value = false
  }
}

async function onDiscard(d: AgentDraft) {
  await ElMessageBox.confirm('确认废弃该 AI 草稿？', '提示', { type: 'warning' })
  await discardDraft(d.id)
  await loadDrafts()
}

onMounted(async () => {
  try {
    const sessions = await listAgentSessions('HANDLE_ASSIST')
    session.value = sessions.find((s) => s.demandId === props.demandId && s.status === 'ACTIVE') || null
  } catch {
    /* 忽略 */
  }
  loadDrafts()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.start-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.draft-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 8px;
}

.draft-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.draft-head .time {
  margin-left: auto;
}

.question-list {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.9;
}

.sol-preview {
  margin-top: 8px;
}

.sol-block {
  margin-bottom: 8px;
}

.sol-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 2px;
}

.sol-block pre {
  margin: 0;
  padding: 6px 8px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow-y: auto;
  font-family: inherit;
}

.draft-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>
