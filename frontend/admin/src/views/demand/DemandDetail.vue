<template>
  <div class="page" v-loading="loading">
    <template v-if="demand">
      <el-card class="head-card">
        <template #header>
          <div class="head">
            <div class="title-area">
              <span class="dno">{{ demand.demandNo || (demand.status === 'DRAFT' ? `草稿 #${demand.id}` : '未编号') }}</span>
              <StatusTag :status="demand.status" :on-hold="demand.onHold" :hold-reason="demand.holdReason" />
              <UrgencyTag :urgency="demand.urgency" />
              <el-tag v-if="isLight" size="small" type="info" effect="plain">轻量提报</el-tag>
              <el-tag v-if="recogLevel" size="small" type="primary" :effect="recogConfirmed ? 'dark' : 'plain'">
                {{ RECOGNITION_LABELS[recogLevel] }}{{ recogConfirmed ? '' : '（AI 判）' }}
              </el-tag>
            </div>
            <div class="actions">
              <el-button v-for="a in flow?.availableActions || []" :key="a.event" size="small"
                         :type="actionType(a.event)" :loading="acting === a.event"
                         @click="onAction(a.event)">{{ a.label }}</el-button>
            </div>
          </div>
        </template>
      </el-card>

      <!-- 打回说明（待补充重提后服务端清除，自动消失） -->
      <el-alert
        v-if="returnReason"
        type="warning"
        show-icon
        :closable="false"
        :title="`打回说明：${returnReason.reason}`"
        :description="`打回人：${returnReason.returnedBy || '—'} · ${returnReason.returnedAt || ''}`"
      />

      <!-- A · 公共要素（横向表单） → 左列（概述 + 要素表单） / 右栏（回放·附件·扩展信息） -->
      <CommonZoneCard :demand="demand" :standard="standard" :quality="quality" />
      <!-- 非科技需求（无要素表单列）：概述全宽独占一行，保持原布局 -->
      <OverviewCard v-if="!(isTech && standard)" :demand="demand" :messages="messages" />

      <el-row :gutter="16">
        <!-- 2026-10-23 调整：概述挪进左列与要素表单同宽，右栏回放因此与概述顶部对齐 -->
        <el-col v-if="isTech && standard" :xs="24" :lg="15" class="main-col">
          <OverviewCard :demand="demand" :messages="messages" />
          <ElementsCard :demand="demand" :standard="standard" :quality="quality" @updated="onElementsUpdated" />
        </el-col>
        <el-col :xs="24" :lg="isTech && standard ? 9 : 24" class="side-col" :class="{ solo: !(isTech && standard) }">
          <ChatReplayCard :messages="messages" class="grow" />
          <AttachmentsCard :demand-id="demand.id" :attachments="attachments" />
          <ExtInfoCard :demand="demand" :standard="standard" />
        </el-col>
      </el-row>

      <el-card>
        <el-tabs v-model="tab">
          <el-tab-pane label="方案" name="solution">
            <SolutionPanel v-if="tab === 'solution'" :demand="demand" @reload="reload" />
          </el-tab-pane>
          <el-tab-pane label="AI 辅助" name="assist">
            <AssistPanel v-if="tab === 'assist'" :demand="demand" />
          </el-tab-pane>
          <el-tab-pane label="沟通记录" name="comment">
            <CommentPanel v-if="tab === 'comment'" :demand-id="demand.id" />
          </el-tab-pane>
          <el-tab-pane label="工时" name="effort">
            <EffortPanel v-if="tab === 'effort'" :demand="demand" />
          </el-tab-pane>
          <el-tab-pane label="关联" name="relation">
            <RelationPanel v-if="tab === 'relation'" :demand-id="demand.id" />
          </el-tab-pane>
          <el-tab-pane label="处理进度" name="progress">
            <template v-if="tab === 'progress'">
              <el-descriptions :column="3" border size="small" class="p-desc">
                <el-descriptions-item label="处理人">{{ demand.assigneeName || '—' }}</el-descriptions-item>
                <el-descriptions-item label="提交时间">{{ demand.submittedAt || '—' }}</el-descriptions-item>
                <el-descriptions-item label="确认时间">{{ demand.confirmedAt || '—' }}</el-descriptions-item>
                <el-descriptions-item label="完成时间">{{ demand.doneAt || '—' }}</el-descriptions-item>
                <el-descriptions-item label="验收评分" :span="2">
                  <template v-if="demand.qualityScore">
                    质量 {{ demand.qualityScore }} 分 / 满意 {{ demand.satisfactionScore }} 分
                  </template>
                  <template v-else>—</template>
                </el-descriptions-item>
                <el-descriptions-item v-if="demand.holdReason" label="挂起原因" :span="3">
                  {{ demand.holdReason }}
                </el-descriptions-item>
                <el-descriptions-item v-if="demand.closeReason" label="关闭原因" :span="3">
                  {{ demand.closeReason }}
                </el-descriptions-item>
              </el-descriptions>
              <el-timeline v-if="flow?.transitions.length" class="timeline">
                <el-timeline-item v-for="t in flow.transitions" :key="t.id" :timestamp="t.createdAt" placement="top">
                  <div class="t-line">
                    <el-tag size="small" :type="t.holdFlag ? 'danger' : 'primary'">{{ t.eventLabel }}</el-tag>
                    <span class="t-status">
                      {{ t.fromStatusLabel ? `${t.fromStatusLabel} → ` : '' }}{{ t.toStatusLabel }}
                    </span>
                    <span class="t-op">{{ t.operatorName || '系统' }}</span>
                  </div>
                  <div v-if="t.comment" class="t-comment">{{ t.comment }}</div>
                </el-timeline-item>
              </el-timeline>
              <el-empty v-else description="暂无流转记录" :image-size="60" />
            </template>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <!-- 分派 -->
      <el-dialog v-model="assignVisible" title="分派处理人" width="420px">
        <el-select v-model="assigneeId" placeholder="选择处理人" class="full">
          <el-option v-for="u in assignees" :key="u.id" :label="`${u.name}${u.department ? '（' + u.department + '）' : ''}`"
                     :value="u.id" />
        </el-select>
        <template #footer>
          <el-button @click="assignVisible = false">取消</el-button>
          <el-button type="primary" :loading="acting === 'ASSIGN'" :disabled="!assigneeId" @click="doAssign">分派</el-button>
        </template>
      </el-dialog>

      <!-- 关闭 -->
      <el-dialog v-model="closeVisible" title="关闭需求" width="480px">
        <el-form label-width="90px">
          <el-form-item label="关闭原因" required>
            <el-input v-model="closeForm.reason" type="textarea" :rows="3" placeholder="必填，如重复/不立项" />
          </el-form-item>
          <el-form-item label="重复关联">
            <el-input-number v-model="closeForm.duplicateOfId" :min="1" :controls="false" placeholder="选填：被重复需求的 ID"
                             class="full" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="closeVisible = false">取消</el-button>
          <el-button type="danger" :loading="acting === 'CLOSE'" :disabled="!closeForm.reason.trim()"
                     @click="doClose">确认关闭</el-button>
        </template>
      </el-dialog>

      <!-- 改型 -->
      <el-dialog v-model="typeVisible" title="类型修正" width="420px">
        <el-select v-model="newTypeCode" class="full">
          <el-option v-for="(label, k) in TYPE_META" :key="k" :label="label" :value="k" />
        </el-select>
        <template #footer>
          <el-button @click="typeVisible = false">取消</el-button>
          <el-button type="primary" :loading="acting === 'CHANGE_TYPE'" :disabled="!newTypeCode || newTypeCode === demand.demandTypeCode"
                     @click="doChangeType">确认修正</el-button>
        </template>
      </el-dialog>

      <!-- 验收通过 -->
      <el-dialog v-model="passVisible" title="验收通过" width="480px">
        <el-form label-width="90px">
          <el-form-item label="质量评分" required>
            <el-rate v-model="passForm.qualityScore" />
          </el-form-item>
          <el-form-item label="满意度评分" required>
            <el-rate v-model="passForm.satisfactionScore" />
          </el-form-item>
          <el-form-item label="验收意见">
            <el-input v-model="passForm.opinion" type="textarea" :rows="3" placeholder="选填" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="passVisible = false">取消</el-button>
          <el-button type="success" :loading="acting === 'ACCEPT_PASS'"
                     :disabled="!passForm.qualityScore || !passForm.satisfactionScore"
                     @click="doAcceptPass">确认通过</el-button>
        </template>
      </el-dialog>

      <!-- 拆分 -->
      <el-dialog v-model="splitVisible" title="拆分子需求" width="640px">
        <div v-for="(item, i) in splitItems" :key="i" class="split-item">
          <el-input v-model="item.title" placeholder="子需求标题（必填）" class="split-title" />
          <el-input v-model="item.summary" placeholder="子需求说明（选填）" type="textarea" :rows="2" />
          <el-button size="small" type="danger" link :disabled="splitItems.length <= 1"
                     @click="splitItems.splice(i, 1)">删除</el-button>
        </div>
        <el-button size="small" @click="splitItems.push({ title: '', summary: '' })">+ 添加一项</el-button>
        <template #footer>
          <el-button @click="splitVisible = false">取消</el-button>
          <el-button type="primary" :loading="acting === 'SPLIT'"
                     :disabled="!splitItems.some(i => i.title.trim())"
                     @click="doSplit">确认拆分</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { demandApi, flowApi, triageApi } from '@/api'
import type {
  AssigneeOption, AttachmentRow, DemandRow, ElementStatus, FlowDetail, MessageRow, StandardDef,
} from '@/api'
import { ApiError } from '@/api/request'
import { TYPE_META } from '@/utils/status'
import { RECOGNITION_LABELS, recognitionLevel, vagueRequiredLabels } from '@/utils/demand'
import StatusTag from '@/components/StatusTag.vue'
import UrgencyTag from '@/components/UrgencyTag.vue'
import SolutionPanel from './panels/SolutionPanel.vue'
import AssistPanel from './panels/AssistPanel.vue'
import CommentPanel from './panels/CommentPanel.vue'
import EffortPanel from './panels/EffortPanel.vue'
import RelationPanel from './panels/RelationPanel.vue'
import CommonZoneCard from './blocks/CommonZoneCard.vue'
import OverviewCard from './blocks/OverviewCard.vue'
import ElementsCard from './blocks/ElementsCard.vue'
import ExtInfoCard from './blocks/ExtInfoCard.vue'
import AttachmentsCard from './blocks/AttachmentsCard.vue'
import ChatReplayCard from './blocks/ChatReplayCard.vue'

const route = useRoute()
const loading = ref(false)
const demand = ref<DemandRow | null>(null)
const flow = ref<FlowDetail | null>(null)
const standard = ref<StandardDef | null>(null)
const quality = ref<ElementStatus[]>([])
const messages = ref<MessageRow[]>([])
const attachments = ref<AttachmentRow[]>([])
const tab = ref((route.query.tab as string) || 'solution')
const acting = ref('')

// 打回说明（ext.returnReason）：管理员打回待补充时服务端写入，重提后清除
const returnReason = computed(() => {
  const v = demand.value?.ext?.returnReason as { reason?: string; returnedBy?: string; returnedAt?: string } | undefined
  return v && typeof v.reason === 'string' && v.reason ? v : null
})

// 科技需求才展示 B/C/D 要素表单（五区 27 要素为科技专属标准）
const isTech = computed(() => demand.value?.demandTypeCode === 'TECH')
// 轻量提报徽标（微需求快速通道 ext.mode.level === 'light'）
const isLight = computed(() => {
  const mode = demand.value?.ext?.mode as { level?: string } | undefined
  return mode?.level === 'light'
})
// 判型徽标：人工确认实心 / AI 置信度判空心
const typeRecognition = computed(() => demand.value?.ext?.typeRecognition)
const recogLevel = computed(() => recognitionLevel(typeRecognition.value))
const recogConfirmed = computed(() => {
  const r = typeRecognition.value as { confirmed?: string | null } | undefined
  return !!r?.confirmed
})

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

// 要素行内编辑保存成功：本地同步最新 demand（revision 推进）与重算后的质量，无需整页刷新
function onElementsUpdated(payload: { demand: DemandRow; quality: ElementStatus[] }) {
  demand.value = payload.demand
  quality.value = payload.quality
}

async function reload() {
  const id = Number(route.params.id)
  loading.value = true
  try {
    const [bundle, f] = await Promise.all([demandApi.detail(id), flowApi.detail(id)])
    demand.value = bundle.demand
    standard.value = bundle.standard
    quality.value = bundle.quality || []
    messages.value = bundle.messages || []
    attachments.value = bundle.attachments || []
    flow.value = f
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
    acting.value = ''
  }
}

// ---- 动作分发 ----
type BtnType = 'primary' | 'success' | 'warning' | 'danger' | 'info'
function actionType(event: string): BtnType {
  if (['CLOSE', 'WITHDRAW', 'RETURN', 'RETURN_POOL', 'REVIEW_REJECT', 'ACCEPT_REJECT'].includes(event)) return 'danger'
  if (event === 'HOLD') return 'warning'
  if (['RESUME', 'ACCEPT_PASS', 'REVIEW_PASS'].includes(event)) return 'success'
  return 'primary'
}

/** 需填原因的动作：走 prompt 弹窗 */
const REASON_EVENTS: Record<string, { title: string; placeholder: string }> = {
  RETURN: { title: '退回补充', placeholder: '请说明需要补充的内容' },
  RETURN_POOL: { title: '退回处理池', placeholder: '请填写退单原因' },
  HOLD: { title: '挂起', placeholder: '请填写挂起原因（如等待业务方确认）' },
  WITHDRAW: { title: '撤销需求', placeholder: '请填写撤销原因' },
  ACCEPT_REJECT: { title: '验收打回', placeholder: '请填写打回意见（必填）' },
}

/** 二次确认即可的动作 */
const CONFIRM_EVENTS: Record<string, string> = {
  ACCEPT: '确认受理该需求？受理后进入「待分派」。',
  CLAIM: '确认领取该需求？领取后由你负责处理。',
  START: '确认开始处理？状态将变为「处理中」。',
  RESUME: '确认恢复处理？将回到挂起前的状态。',
  SUBMIT_ACCEPTANCE: '提交验收前请确认：方案已通过评审、工时已填报、交付物已上传。确认提交？',
}

async function promptReason(event: string): Promise<string | null> {
  const cfg = REASON_EVENTS[event]
  // 受理兜底（2026-10-25 三段防线③）：打回时预填笼统必填项清单作为补充说明草稿，管理员可删改——
  // 清单口径与提报侧「合并一问」一致，省得逐条手敲；没有笼统项时保持空白不预填
  const vague = event === 'RETURN' ? vagueRequiredLabels(standard.value, quality.value) : []
  const prefill = vague.length ? `请补充以下写得比较笼统的内容：${vague.map(label => `「${label}」`).join('、')}。` : ''
  try {
    const { value } = await ElMessageBox.prompt(cfg.placeholder, cfg.title, {
      inputValue: prefill,
      inputPlaceholder: cfg.placeholder,
      inputValidator: (v: string) => (v && v.trim() ? true : '原因必填'),
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    return (value as string).trim()
  } catch {
    return null
  }
}

async function run(event: string, fn: () => Promise<unknown>, success: string) {
  acting.value = event
  try {
    await fn()
    ElMessage.success(success)
  } catch (e) {
    ElMessage.error(errorMessage(e, '操作失败'))
  } finally {
    await reload()
  }
}

async function onAction(event: string) {
  if (!demand.value) return
  const id = demand.value.id

  // 方案相关动作切到方案 Tab 处理
  if (['SUBMIT_REVIEW', 'REVIEW_PASS', 'REVIEW_REJECT'].includes(event)) {
    tab.value = 'solution'
    ElMessage.info('请在「方案」页签中操作')
    return
  }
  if (event in REASON_EVENTS) {
    const reason = await promptReason(event)
    if (!reason) return
    if (event === 'RETURN') return run(event, () => triageApi.returnDemand(id, reason), '已退回补充')
    if (event === 'RETURN_POOL') return run(event, () => triageApi.returnPool(id, reason), '已退回处理池')
    if (event === 'HOLD') return run(event, () => flowApi.hold(id, reason), '已挂起')
    if (event === 'WITHDRAW') return run(event, () => demandApi.close(id, reason), '已撤销')
    if (event === 'ACCEPT_REJECT') {
      return run(event, () => flowApi.acceptanceReview(id, { result: 'REJECT', opinion: reason }), '已打回，回到「处理中」')
    }
  }
  if (event in CONFIRM_EVENTS) {
    // 受理兜底（2026-10-25 三段防线③）：受理前若仍有笼统必填项，前置汇总提醒，让受理人知情后再确认
    let message: string = CONFIRM_EVENTS[event]
    if (event === 'ACCEPT') {
      const vague = vagueRequiredLabels(standard.value, quality.value)
      if (vague.length) {
        const names = vague.slice(0, 3).map(label => `「${label}」`).join('、') + (vague.length > 3 ? ' 等' : '')
        message = `该需求还有 ${vague.length} 项必填内容写得比较笼统（${names}），受理后需补充调研。` + message
      }
    }
    try {
      await ElMessageBox.confirm(message, '操作确认',
        { type: 'warning', confirmButtonText: '确定', cancelButtonText: '取消' })
    } catch { return }
    if (event === 'ACCEPT') return run(event, () => triageApi.accept(id), '已受理')
    if (event === 'CLAIM') return run(event, () => triageApi.claim(id), '已领取')
    if (event === 'START') return run(event, () => flowApi.start(id), '已开始处理')
    if (event === 'RESUME') return run(event, () => flowApi.resume(id), '已恢复')
    if (event === 'SUBMIT_ACCEPTANCE') return run(event, () => flowApi.submitAcceptance(id), '已提交验收')
  }
  if (event === 'ASSIGN') return openAssign()
  if (event === 'CLOSE') { closeVisible.value = true; return }
  if (event === 'CHANGE_TYPE') { newTypeCode.value = ''; typeVisible.value = true; return }
  if (event === 'ACCEPT_PASS') { passVisible.value = true; return }
  if (event === 'SPLIT') return openSplit()
}

// ---- 分派 ----
const assignVisible = ref(false)
const assignees = ref<AssigneeOption[]>([])
const assigneeId = ref<number>()

async function openAssign() {
  if (!demand.value) return
  // 候选人按该需求类型过滤（类型权限），不可跨单缓存
  try {
    assignees.value = await triageApi.assignees(demand.value.demandTypeCode ?? '')
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载处理人失败'))
    return
  }
  assigneeId.value = undefined
  assignVisible.value = true
}

async function doAssign() {
  if (!demand.value || !assigneeId.value) return
  await run('ASSIGN', () => triageApi.assign(demand.value!.id, assigneeId.value!), '已分派')
  assignVisible.value = false
}

// ---- 关闭 ----
const closeVisible = ref(false)
const closeForm = reactive({ reason: '', duplicateOfId: undefined as number | undefined })

async function doClose() {
  if (!demand.value) return
  await run('CLOSE', () => triageApi.close(
    demand.value!.id, closeForm.reason.trim(), closeForm.duplicateOfId || undefined), '已关闭')
  closeVisible.value = false
  closeForm.reason = ''
  closeForm.duplicateOfId = undefined
}

// ---- 改型 ----
const typeVisible = ref(false)
const newTypeCode = ref('')

async function doChangeType() {
  if (!demand.value || !newTypeCode.value) return
  await run('CHANGE_TYPE', () => triageApi.changeType(demand.value!.id, newTypeCode.value), '类型已修正')
  typeVisible.value = false
}

// ---- 验收通过 ----
const passVisible = ref(false)
const passForm = reactive({ qualityScore: 0, satisfactionScore: 0, opinion: '' })

async function doAcceptPass() {
  if (!demand.value) return
  await run('ACCEPT_PASS', () => flowApi.acceptanceReview(demand.value!.id, {
    result: 'PASS',
    qualityScore: passForm.qualityScore,
    satisfactionScore: passForm.satisfactionScore,
    opinion: passForm.opinion.trim() || undefined,
  }), '验收通过，需求已完成')
  passVisible.value = false
  passForm.qualityScore = 0
  passForm.satisfactionScore = 0
  passForm.opinion = ''
}

// ---- 拆分 ----
const splitVisible = ref(false)
const splitItems = ref<{ title: string; summary: string }[]>([])

function openSplit() {
  // 提报时 AI 预判的待拆项作为默认值（若有）
  const pending = demand.value?.ext?.pendingSplits
  if (Array.isArray(pending) && pending.length) {
    splitItems.value = pending.map((p: unknown) => {
      const o = (p || {}) as { title?: string; summary?: string }
      return { title: o.title || '', summary: o.summary || '' }
    })
  } else {
    splitItems.value = [{ title: '', summary: '' }]
  }
  splitVisible.value = true
}

async function doSplit() {
  if (!demand.value) return
  const items = splitItems.value
    .filter(i => i.title.trim())
    .map(i => ({ title: i.title.trim(), summary: i.summary.trim() || undefined }))
  await run('SPLIT', () => flowApi.split(demand.value!.id, items), '已拆分，子需求进入「待分派」')
  splitVisible.value = false
}

// 关联页跳转其他需求时复用本组件，需按路由参数重载
watch(() => route.params.id, () => {
  if (route.params.id) reload()
})

onMounted(reload)
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.title-area { display: flex; align-items: center; gap: 10px; }
.dno { font-weight: 600; }
/* 头部卡只有一行内容：压掉空 body 与多余内边距，避免浪费高度 */
.head-card :deep(.el-card__header) { padding: 10px 16px; }
.head-card :deep(.el-card__body) { display: none; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.card-title { font-weight: 600; }
.full { width: 100%; }
.p-desc { margin-bottom: 16px; }
/* 右栏跟随左栏：el-col 拉伸为行高后变纵向 flex 容器，回放卡（.grow）吃掉剩余高度 */
.main-col { display: flex; flex-direction: column; gap: 16px; }
.side-col { display: flex; flex-direction: column; gap: 16px; }
.side-col > .grow { flex: 1 1 auto; min-height: 0; }
/* 整行独占模式（物料/培训无左栏）：回放卡回归自然高度并限高，避免长对话撑爆页面 */
.side-col.solo > .grow { flex: none; }
.side-col.solo > .grow :deep(.replay) { max-height: 720px; }
.timeline { padding-left: 4px; }
.t-line { display: flex; align-items: center; gap: 10px; }
.t-status { font-size: 13px; }
.t-op { color: #909399; font-size: 12px; }
.t-comment { color: #606266; font-size: 12px; margin-top: 4px; }
.split-item { display: flex; flex-direction: column; gap: 6px; padding: 10px; border: 1px solid #ebeef5; border-radius: 4px; margin-bottom: 10px; }
.split-title { font-weight: 600; }
</style>
