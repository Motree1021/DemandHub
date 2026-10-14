<template>
  <div class="assist">
    <!-- 相似历史需求：打开面板即检索（已完成需求的向量化知识库召回），点击可跳转对照 -->
    <div class="block">
      <div class="block-head">
        <span class="block-title">相似历史需求</span>
        <el-button size="small" text :loading="similarLoading" @click="loadSimilar">刷新</el-button>
      </div>
      <div v-loading="similarLoading">
        <div v-if="similar.length" class="similar-list">
          <div v-for="hit in similar" :key="hit.demandId" class="similar-item" @click="goDetail(hit.demandId)">
            <div class="similar-main">
              <span class="similar-no">{{ hit.demandNo }}</span>
              <el-tag v-if="hit.demandTypeCode" size="small" effect="plain">
                {{ TYPE_META[hit.demandTypeCode] || hit.demandTypeCode }}
              </el-tag>
              <span class="similar-title">{{ hit.title }}</span>
            </div>
            <el-progress class="similar-score" :percentage="Math.round(hit.score * 100)" :stroke-width="8" />
          </div>
        </div>
        <el-empty v-else description="暂无相似历史需求" :image-size="48" />
      </div>
    </div>

    <el-divider class="gap" />

    <!-- AI 辅助草稿区：生成物一律先进草稿，人工确认后才进入方案库 -->
    <div class="block">
      <div class="block-head">
        <span class="block-title">AI 辅助</span>
        <span class="block-tip">AI 生成内容仅供参考，人工确认后才会进入方案库</span>
      </div>
      <div class="bar">
        <el-button size="small" type="primary" plain :loading="acting === 'questions'" @click="generate('questions')">
          生成调研问题清单
        </el-button>
        <el-button size="small" type="primary" plain :loading="acting === 'solution'" @click="generate('solution')">
          生成方案草稿
        </el-button>
      </div>

      <el-empty v-if="!drafts.length" description="暂无草稿，点击上方按钮生成" :image-size="48" />
      <div v-for="d in drafts" :key="d.id" class="draft" :class="{ done: d.status !== 'PENDING' }">
        <div class="draft-head">
          <el-tag size="small" :type="d.draftType === 'QUESTIONS' ? 'info' : 'primary'" effect="plain">
            {{ d.draftType === 'QUESTIONS' ? '调研问题' : '方案草稿' }}
          </el-tag>
          <el-tag v-if="d.status === 'PENDING'" size="small" type="warning">AI 生成，待人工确认</el-tag>
          <el-tag v-else-if="d.status === 'CONFIRMED'" size="small" type="success">已确认入库</el-tag>
          <el-tag v-else size="small" type="info">已废弃</el-tag>
          <span class="draft-time">{{ d.createdAt }}</span>
          <span class="grow" />
          <template v-if="d.status === 'PENDING'">
            <el-button v-if="d.draftType === 'SOLUTION'" size="small" type="primary" link
                       :disabled="!canConfirm"
                       :title="canConfirm ? '' : '需求处于「分析中」时才能确认入库'"
                       @click="openConfirm(d)">编辑并确认入库</el-button>
            <el-button size="small" type="danger" link :loading="acting === `discard-${d.id}`"
                       @click="discard(d)">废弃</el-button>
          </template>
        </div>
        <!-- 问题清单：每条一行，序号呈现 -->
        <ol v-if="d.draftType === 'QUESTIONS' && Array.isArray(d.content)" class="q-list">
          <li v-for="(q, i) in d.content" :key="i">{{ q }}</li>
        </ol>
        <!-- 方案草稿：折叠展示全文，避免长文撑开列表 -->
        <el-collapse v-else-if="!Array.isArray(d.content)" class="s-collapse">
          <el-collapse-item title="查看草稿内容">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item label="需求理解">
                <pre class="pre">{{ d.content.specContent || '—' }}</pre>
              </el-descriptions-item>
              <el-descriptions-item label="方案内容">
                <pre class="pre">{{ d.content.solutionContent || '—' }}</pre>
              </el-descriptions-item>
            </el-descriptions>
          </el-collapse-item>
        </el-collapse>
      </div>
    </div>

    <!-- 确认入库：可在 AI 原文基础上修订；保存后作为新方案版本（草稿态）进入「方案」页签 -->
    <el-dialog v-model="confirmVisible" title="确认方案入库" width="720px">
      <el-alert type="info" show-icon :closable="false" class="confirm-tip"
                title="确认后将作为新方案版本（草稿状态）进入「方案」页签，后续可继续编辑、提交评审" />
      <el-form label-width="90px">
        <el-form-item label="需求理解">
          <el-input v-model="confirmForm.specContent" type="textarea" :rows="4" placeholder="要做什么、做到什么程度" />
        </el-form-item>
        <el-form-item label="方案内容">
          <el-input v-model="confirmForm.solutionContent" type="textarea" :rows="6" placeholder="怎么做、步骤与资源" />
        </el-form-item>
        <el-form-item label="计划交付">
          <el-date-picker v-model="confirmForm.planDeliveryAt" type="date" value-format="YYYY-MM-DD"
                          placeholder="选择日期" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="acting === 'confirm'" @click="doConfirm">确认入库</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { assistApi, ragApi } from '@/api'
import type { AgentSessionRow, AssistDraftRow, DemandRow, SimilarHit } from '@/api'
import { ApiError } from '@/api/request'
import { TYPE_META } from '@/utils/status'

const props = defineProps<{ demand: DemandRow }>()
const router = useRouter()

const acting = ref('')
const session = ref<AgentSessionRow | null>(null)
const drafts = ref<AssistDraftRow[]>([])
const similar = ref<SimilarHit[]>([])
const similarLoading = ref(false)

/** 方案确认入库要求需求处于「分析中」（后端同样强校验） */
const canConfirm = computed(() => props.demand.status === 'ANALYZING')

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function loadDrafts() {
  try {
    drafts.value = await assistApi.drafts(props.demand.id)
  } catch (e) {
    ElMessage.error(errorMessage(e, '草稿加载失败'))
  }
}

async function loadSimilar() {
  similarLoading.value = true
  try {
    similar.value = await ragApi.similar(props.demand.id)
  } catch (e) {
    ElMessage.error(errorMessage(e, '相似需求检索失败'))
  } finally {
    similarLoading.value = false
  }
}

function goDetail(id: number) {
  router.push({ name: 'demand-detail', params: { id } })
}

/** 会话为需求级共享：首次生成时创建，之后复用 */
async function ensureSession(): Promise<AgentSessionRow | null> {
  if (session.value) return session.value
  try {
    session.value = await assistApi.openSession(props.demand.id)
    return session.value
  } catch (e) {
    ElMessage.error(errorMessage(e, '辅助工作区创建失败'))
    return null
  }
}

async function generate(kind: 'questions' | 'solution') {
  const s = await ensureSession()
  if (!s) return
  acting.value = kind
  try {
    if (kind === 'questions') {
      await assistApi.generateQuestions(s.id)
      ElMessage.success('调研问题清单已生成，请人工核对')
    } else {
      await assistApi.generateSolution(s.id)
      ElMessage.success('方案草稿已生成，请人工核对后确认入库')
    }
    await loadDrafts()
  } catch (e) {
    ElMessage.error(errorMessage(e, 'AI 生成失败，请稍后再试'))
  } finally {
    acting.value = ''
  }
}

// ---- 确认入库 ----
const confirmVisible = ref(false)
const confirmRow = ref<AssistDraftRow | null>(null)
const confirmForm = reactive({ specContent: '', solutionContent: '', planDeliveryAt: '' })

function openConfirm(d: AssistDraftRow) {
  if (Array.isArray(d.content)) return
  confirmRow.value = d
  // 预填 AI 原文供修订；不改动直接确认则按原文入库（后端同口径）
  confirmForm.specContent = d.content.specContent || ''
  confirmForm.solutionContent = d.content.solutionContent || ''
  confirmForm.planDeliveryAt = props.demand.expectDeliveryAt || ''
  confirmVisible.value = true
}

async function doConfirm() {
  if (!confirmRow.value) return
  acting.value = 'confirm'
  try {
    await assistApi.confirm(confirmRow.value.id, {
      specContent: confirmForm.specContent.trim() || undefined,
      solutionContent: confirmForm.solutionContent.trim() || undefined,
      planDeliveryAt: confirmForm.planDeliveryAt || undefined,
    })
    ElMessage.success('已入库，请到「方案」页签查看新版本')
    confirmVisible.value = false
    await loadDrafts()
  } catch (e) {
    ElMessage.error(errorMessage(e, '确认入库失败'))
  } finally {
    acting.value = ''
  }
}

// ---- 废弃 ----
async function discard(d: AssistDraftRow) {
  try {
    await ElMessageBox.confirm('废弃后草稿不可恢复，确认废弃？', '废弃草稿',
      { type: 'warning', confirmButtonText: '废弃', cancelButtonText: '取消' })
  } catch { return }
  acting.value = `discard-${d.id}`
  try {
    await assistApi.discard(d.id)
    ElMessage.success('已废弃')
    await loadDrafts()
  } catch (e) {
    ElMessage.error(errorMessage(e, '操作失败'))
  } finally {
    acting.value = ''
  }
}

onMounted(() => {
  loadDrafts()
  loadSimilar()
})
</script>

<style scoped>
.assist { display: flex; flex-direction: column; }
.block-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.block-title { font-weight: 600; }
.block-tip { color: #909399; font-size: 12px; }
.gap { margin: 16px 0; }
.bar { display: flex; gap: 8px; margin-bottom: 12px; }
.similar-list { display: flex; flex-direction: column; gap: 8px; }
.similar-item {
  display: flex; align-items: center; gap: 16px; padding: 8px 12px;
  border: 1px solid #ebeef5; border-radius: 4px; cursor: pointer;
}
.similar-item:hover { border-color: #c6e2ff; background: #f5f9ff; }
.similar-main { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; }
.similar-no { color: #909399; font-size: 12px; flex-shrink: 0; }
.similar-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.similar-score { width: 140px; flex-shrink: 0; }
.draft { border: 1px solid #ebeef5; border-radius: 4px; padding: 10px 12px; margin-bottom: 10px; }
.draft.done { opacity: 0.75; background: #fafafa; }
.draft-head { display: flex; align-items: center; gap: 8px; }
.draft-time { color: #909399; font-size: 12px; }
.grow { flex: 1; }
.q-list { margin: 10px 0 0; padding-left: 20px; color: #303133; }
.q-list li { margin-bottom: 4px; }
.s-collapse { margin-top: 10px; }
.s-collapse :deep(.el-collapse-item__header) { font-size: 13px; color: #606266; }
.pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; }
.confirm-tip { margin-bottom: 12px; }
</style>
