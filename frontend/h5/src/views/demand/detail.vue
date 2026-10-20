<template>
  <app-layout>
    <van-loading v-if="loading" class="page-loading">加载详情…</van-loading>
    <template v-else-if="detail">
      <van-notice-bar v-if="receipt" mode="closeable" left-icon="volume-o" wrapable :scrollable="false" class="receipt">{{ receipt }}</van-notice-bar>
      <van-notice-bar v-if="demand.onHold" left-icon="pause-circle-o" wrapable :scrollable="false" color="#c2410c" background="#fff7ed">
        需求已挂起：{{ demand.holdReason || '处理人暂缓处理，恢复后会继续' }}
      </van-notice-bar>
      <div class="detail-card header"><div class="number">{{ demand.demandNo || `草稿 #${demand.id}` }}</div><h1>{{ demand.title || '未命名草稿' }}</h1><div class="tags"><van-tag type="primary" plain>{{ statusLabel(demand.status) }}</van-tag><van-tag plain>{{ detail.standard?.name || typeLabel(demand.demandTypeCode) }}</van-tag><van-tag v-if="isLight" type="success" plain>轻量提报</van-tag><van-tag :type="demand.urgency === 'NORMAL' ? 'default' : 'danger'">{{ urgencyLabel(demand.urgency) }}</van-tag></div><div class="meta"><span>期望交付：{{ demand.expectDeliveryAt || '未填写' }}</span><span>{{ demand.status === 'DRAFT' ? '保存' : '提交' }}时间：{{ fmtTime(demand.submittedAt || demand.updatedAt) }}</span><span v-if="demand.submitterName">提报人：{{ demand.submitterName }} {{ demand.submitterDept || '' }}</span><span v-if="demand.assigneeName">处理人：{{ demand.assigneeName }}</span><span v-if="demand.qualityScore">验收评分：质量 {{ demand.qualityScore }} 分 · 满意 {{ demand.satisfactionScore }} 分</span></div></div>
      <div class="detail-card"><h2>需求概述</h2><template v-if="overviewRows.length"><div v-for="row in overviewRows" :key="row.key" class="ov-row"><strong>{{ row.label }}</strong><p>{{ row.text }}</p></div></template><template v-else><p class="content">{{ demand.content || '尚未填写' }}</p><template v-if="userSupplements.length"><h3 class="supp-title">后续对话中的补充原话</h3><div v-for="m in userSupplements" :key="m.id" class="supp-row"><small>{{ fmtTime(m.createdAt) }}</small><p>{{ m.content }}</p></div></template></template></div>
      <div v-if="flowRows.length" class="detail-card"><h2>处理进度</h2><div v-for="t in flowRows" :key="t.id" class="flow-row"><span class="flow-dot" aria-hidden="true"></span><div class="flow-body"><div class="flow-line"><strong>{{ t.eventLabel }}</strong><span v-if="t.toStatus !== t.fromStatus" class="flow-status">{{ t.fromStatus ? statusLabel(t.fromStatus) + ' → ' : '' }}{{ statusLabel(t.toStatus) }}</span></div><small>{{ fmtTime(t.createdAt) }}<template v-if="t.operatorName"> · {{ t.operatorName }}</template></small><p v-if="t.comment" class="flow-comment">{{ t.comment }}</p></div></div></div>
      <div v-if="attachments.length" class="detail-card">
        <h2>附件（{{ attachments.length }}）</h2>
        <p class="att-note">AI 暂不支持识别附件内容，附件将作为需求材料随需求一并提交。</p>
        <van-swipe-cell v-for="att in attachments" :key="att.id" class="att-cell">
          <div class="att-row" @click="downloadAttachmentFile(att)">
            <van-icon :name="att.kind === 'IMAGE' ? 'photo-o' : 'description'" class="att-icon" />
            <span class="att-meta"><strong>{{ att.fileName }}</strong><small>{{ att.kindLabel }} · {{ fmtSize(att.size) }} · 点击下载</small></span>
          </div>
          <template #right>
            <van-button v-if="canDeleteAttachment" square type="danger" text="删除" class="att-delete" @click="removeAttachment(att)" />
          </template>
        </van-swipe-cell>
      </div>
      <div v-if="detail.messages.length" class="detail-card playback"><van-collapse v-model="expanded"><van-collapse-item title="AI 对话回放" name="messages"><div v-for="message in detail.messages" :key="message.id" class="history-row" :class="`from-${message.role.toLowerCase()}`"><div class="bubble"><div class="bubble-head"><strong>{{ message.role === 'USER' ? '你' : message.role === 'ASSISTANT' ? 'AI 提报助手' : '系统' }}</strong><small>{{ fmtTime(message.createdAt) }}</small></div><p>{{ message.content }}</p></div></div></van-collapse-item></van-collapse></div>
      <template v-for="group in zoneGroups" :key="group.zone">
        <div v-if="group.rows.length || demand.status === 'DRAFT'" class="detail-card"><h2>{{ group.title }}</h2><div v-for="item in group.rows" :key="item.path" class="ext-row"><strong>{{ item.label }}</strong><span>{{ item.value }}</span></div><p v-if="!group.rows.length" class="zone-empty">暂未提取到信息，待补充。</p></div>
      </template>
      <div v-if="extensionFields.length" class="detail-card"><h2>补充信息</h2><div v-for="item in extensionFields" :key="item.path" class="ext-row"><strong>{{ item.label }}</strong><span>{{ item.value }}</span></div></div>
      <div class="detail-card playback"><van-collapse v-model="expanded"><van-collapse-item title="信息完备度" name="quality"><quality-list :elements="detail.quality" :labels="labels" /></van-collapse-item></van-collapse></div>
      <div v-if="demand.status === 'CLOSED'" class="detail-card"><h2>撤销说明</h2><p class="content">{{ demand.closeReason }}</p><small>{{ fmtTime(demand.closedAt) }}</small></div>
      <div v-if="returnReason" class="detail-card return-card"><h2>打回说明</h2><p class="content">{{ returnReason.reason }}</p><small>打回人：{{ returnReason.returnedBy || '产品经理' }} · {{ fmtTime(returnReason.returnedAt || undefined) }}</small></div>
      <div class="detail-card actions">
        <template v-if="own && demand.status === 'ACCEPTANCE'">
          <van-button block type="success" @click="passVisible = true">验收通过</van-button>
          <van-button block plain type="warning" @click="rejectVisible = true">验收打回</van-button>
        </template>
        <van-button block plain type="primary" :loading="downloading" @click="download">下载 Markdown</van-button>
        <van-button v-if="own && demand.status === 'DRAFT'" block type="primary" @click="router.push({ path: '/report', query: { draftId: demand.id } })">继续编辑草稿</van-button>
        <van-button v-if="own && demand.status === 'NEED_INFO'" block type="primary" @click="router.push({ path: '/report', query: { draftId: demand.id } })">去补充，重新提交</van-button>
        <van-button v-if="isAdmin && demand.status === 'SUBMITTED' && !own" block type="warning" @click="returnVisible = true">打回补充</van-button>
        <van-button v-if="own && (demand.status === 'SUBMITTED' || demand.status === 'DRAFT' || demand.status === 'NEED_INFO')" block plain type="danger" @click="closeVisible = true">{{ demand.status === 'DRAFT' ? '撤销草稿' : '撤销需求' }}</van-button>
        <van-button block plain @click="router.push(user.userInfo?.isAdmin && !own ? '/admin' : '/mine')">{{ user.userInfo?.isAdmin && !own ? '返回需求整理' : '返回我的需求' }}</van-button>
      </div>
    </template>
    <van-empty v-else description="详情加载失败"><van-button size="small" type="primary" @click="fetchDetail">重试</van-button></van-empty>
    <van-dialog v-model:show="closeVisible" :title="detail?.demand.status === 'DRAFT' ? '撤销草稿' : '撤销需求'" show-cancel-button :before-close="beforeClose"><van-field v-model="reason" type="textarea" rows="3" label="撤销原因" maxlength="256" placeholder="请填写撤销原因" /></van-dialog>
    <van-dialog v-model:show="returnVisible" title="打回补充" show-cancel-button :before-close="beforeReturn"><van-field v-model="returnReasonText" type="textarea" rows="3" label="打回原因" maxlength="256" placeholder="请说明还缺哪些信息，提报人会看到这段话" /></van-dialog>
    <van-dialog v-model:show="passVisible" title="验收通过" show-cancel-button :before-close="beforePass">
      <div class="rate-row"><span class="rate-label">质量评分</span><van-rate v-model="passForm.qualityScore" /></div>
      <div class="rate-row"><span class="rate-label">满意度评分</span><van-rate v-model="passForm.satisfactionScore" /></div>
      <van-field v-model="passForm.opinion" type="textarea" rows="3" label="验收意见" maxlength="2000" placeholder="选填" />
    </van-dialog>
    <van-dialog v-model:show="rejectVisible" title="验收打回" show-cancel-button :before-close="beforeReject">
      <van-field v-model="rejectOpinion" type="textarea" rows="3" label="打回意见" maxlength="2000" placeholder="必填：说明哪些地方没达到预期，处理人会看到这段话" />
    </van-dialog>
  </app-layout>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showConfirmDialog, showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import QualityList from '@/components/QualityList.vue'
import { getDemand, closeDemand, downloadMarkdown, deleteAttachment, downloadAttachment, fmtSize, parseAttachmentPayload, returnDemand, returnReasonOf, demandModeOf, getFlow, acceptanceReview, type DemandAttachment, type DemandDetail, type FlowDetail, type StandardField } from '@/api/demand'
import { useUserStore } from '@/store/user'
import { allFields, fieldPath, readField } from '@/utils/form'
import { fmtTime, statusLabel, typeLabel, urgencyLabel } from '@/utils/format'
const route = useRoute(); const router = useRouter(); const user = useUserStore()
const detail = ref<DemandDetail | null>(null); const loading = ref(true); const downloading = ref(false)
const expanded = ref<string[]>([]); const closeVisible = ref(false); const reason = ref('')
const returnVisible = ref(false); const returnReasonText = ref('')
// P2：状态时间线（处理进度卡片）
const flow = ref<FlowDetail | null>(null)
const flowRows = computed(() => (flow.value?.transitions || []).slice().reverse())
// P2：回执播报——比对本机记住的上次状态，变化才播；播报一次后记住新状态，关闭横幅不再重复
const receipt = ref('')
const RECEIPT_TEXT: Record<string, string> = {
  SUBMITTED: '提交成功，已送受理', NEED_INFO: '需求被打回补充，请查看「打回说明」',
  TRIAGE: '需求已受理，等待分派处理人', ANALYZING: '处理人已接手，正在分析方案',
  SOLUTION_REVIEW: '方案已提交评审', CONFIRMED: '方案已通过评审确认，即将开始处理',
  IN_PROGRESS: '需求正在处理中', ACCEPTANCE: '处理完成，请你验收',
  DONE: '验收通过，需求已完成', CLOSED: '需求已关闭',
}
// 同一目标态、不同事件的口径细分（看最新一条留痕）
const EVENT_RECEIPT_TEXT: Record<string, string> = {
  ACCEPT_REJECT: '验收未通过，已打回给处理人继续完善',
  REVIEW_REJECT: '方案评审未通过，处理人正在完善方案',
  RESUME: '需求已恢复处理',
}
function updateReceipt() {
  if (!detail.value) return
  const current = demand.value.status
  const key = `demandhub_h5_flow_${demand.value.id}`
  const prev = localStorage.getItem(key)
  if (prev && prev !== current) {
    const latest = flow.value?.transitions?.[flow.value.transitions.length - 1]
    receipt.value = (latest && EVENT_RECEIPT_TEXT[latest.event]) || RECEIPT_TEXT[current] || `需求状态已更新为「${statusLabel(current)}」`
  }
  localStorage.setItem(key, current)
}
// P2：验收操作区（提报人在「待验收」态可见）
const passVisible = ref(false)
const passForm = ref({ qualityScore: 0, satisfactionScore: 0, opinion: '' })
const rejectVisible = ref(false)
const rejectOpinion = ref('')
async function beforePass(action: string): Promise<boolean> {
  if (action === 'cancel') return true
  if (!passForm.value.qualityScore || !passForm.value.satisfactionScore) { showToast('请完成两项评分'); return false }
  try {
    await acceptanceReview(demand.value.id, {
      result: 'PASS', qualityScore: passForm.value.qualityScore,
      satisfactionScore: passForm.value.satisfactionScore, opinion: passForm.value.opinion.trim() || undefined,
    })
    await fetchDetail(); showToast('验收通过，需求已完成'); return true
  } catch { return false }
}
async function beforeReject(action: string): Promise<boolean> {
  if (action === 'cancel') return true
  if (!rejectOpinion.value.trim()) { showToast('请填写打回意见'); return false }
  try {
    await acceptanceReview(demand.value.id, { result: 'REJECT', opinion: rejectOpinion.value.trim() })
    await fetchDetail(); showToast('已打回，处理人会继续完善'); return true
  } catch { return false }
}
const demand = computed(() => detail.value!.demand)
// 方案④口径显性化：快速通道需求详情页可见口径，与列表「轻量」角标同源
const isLight = computed(() => demandModeOf(demand.value) === 'light')
// 需求概述：AI 每轮基于最新表单重写的四段式摘要（ext.overview），固定顺序固定标签；旧草稿无概述时回退展示 A8 原文与补充原话
const OVERVIEW_LABELS: Record<string, string> = { problem: '问题/机会', userScene: '用户&场景', goal: '目标&期望效果', acceptance: '验收标准' }
const overviewRows = computed(() => {
  const overview = ((demand.value?.ext?.overview || {}) as Record<string, unknown>)
  return Object.entries(OVERVIEW_LABELS).filter(([key]) => typeof overview[key] === 'string' && overview[key]).map(([key, label]) => ({ key, label, text: String(overview[key]) }))
})
// 提报人补充原话（方案乙：展示层聚合，A8 底稿不动）：排除与 content 全等的首条 USER 消息（即 A8 底稿），其余用户消息按时间序；附件上传动作消息是操作记录不是原话，与服务端 user_supplements 同口径排除
const userSupplements = computed(() => {
  if (!detail.value) return []
  const base = (demand.value.content || '').trim()
  let skipped = false
  return detail.value.messages.filter(m => {
    if (m.role !== 'USER') return false
    if (parseAttachmentPayload(m.structuredPayload)) return false
    if (!skipped && base && m.content.trim() === base) { skipped = true; return false }
    return true
  })
})
const own = computed(() => demand.value.submitterId === user.userInfo?.id)
// 打回待补充（方案③）：ADMIN 可打回已提交需求；打回原因随 ext.returnReason 展示，重提成功后服务端清除
const isAdmin = computed(() => !!user.userInfo?.isAdmin)
const returnReason = computed(() => returnReasonOf(demand.value))
// 附件区（阶段一）：详情接口随 detail 返回；仅草稿且本人可删（服务端同口径校验）
const attachments = computed<DemandAttachment[]>(() => detail.value?.attachments || [])
const canDeleteAttachment = computed(() => own.value && demand.value.status === 'DRAFT')
const labels = computed(() => Object.fromEntries((detail.value?.standard ? allFields(detail.value.standard) : []).map(field => [field.key, field.label])))
function display(value: unknown) { return value == null || value === '' ? '空' : Array.isArray(value) ? value.join('、') : typeof value === 'object' ? JSON.stringify(value) : String(value) }
// 五区展示（PRD §4.1 详情页要求）：按 A/B/C/D 分组呈现已填要素；ext 为 MATL/TRAIN 与兼容字段兜底；草稿态空分区卡片保留并显示"待补充"占位
const ZONE_TITLES = { A: 'A · 公共要素', B: 'B · 业务需求（Why）', C: 'C · 用户需求（Who/What）', D: 'D · 功能需求（How）' } as const
const zoneGroups = computed(() => {
  if (!detail.value?.standard) return []
  const fields = allFields(detail.value.standard).filter(field => fieldPath(field).startsWith('elements.'))
  return Object.entries(ZONE_TITLES).map(([zone, title]) => ({
    zone, title,
    rows: fields.filter(field => field.zone === zone).map(field => {
      const raw = readField(demand.value, field)
      if (raw == null || raw === '' || (Array.isArray(raw) && !raw.length)) return null
      return { path: fieldPath(field), label: field.label, value: field.options?.[String(raw)] || display(raw) }
    }).filter((item): item is { path: string; label: string; value: string } => item !== null)
  }))
})
const extensionFields = computed(() => {
  if (!detail.value) return []
  const standard = detail.value.standard
  const fields: StandardField[] = standard ? allFields(standard).filter(field => fieldPath(field).startsWith('ext.')) : Object.keys(demand.value.ext || {}).map(key => ({ key, label: key, path: `ext.${key}`, kind: 'text' as const }))
  return fields.map(field => { const value = readField(demand.value, field); return { path: fieldPath(field), label: field.label, value: field.options?.[String(value)] || (value == null || value === '' ? '未填写' : String(value)) } }).filter(item => item.value !== '未填写')
})
async function fetchDetail() {
  loading.value = true
  try {
    detail.value = await getDemand(Number(route.params.id))
  } catch { detail.value = null } finally { loading.value = false }
  if (!detail.value) return
  // 时间线后台加载，不阻塞详情与后续动作提示；失败静默（如无权限场景）只影响进度卡与播报细分口径
  const id = demand.value.id
  getFlow(id).then(f => { flow.value = f }).catch(() => { flow.value = null }).finally(updateReceipt)
}
async function download() { downloading.value = true; try { await downloadMarkdown(demand.value.id, demand.value.demandNo || `draft-${demand.value.id}`) } catch (error) { showToast(error instanceof Error ? error.message : '下载失败') } finally { downloading.value = false } }
async function downloadAttachmentFile(att: DemandAttachment) {
  try { await downloadAttachment(demand.value.id, att.id, att.fileName) } catch (error) { showToast(error instanceof Error ? error.message : '下载失败') }
}
async function removeAttachment(att: DemandAttachment) {
  try { await showConfirmDialog({ title: '删除附件', message: `确定删除「${att.fileName}」吗？删除后不可恢复。` }) } catch { return }
  try { await deleteAttachment(demand.value.id, att.id); await fetchDetail(); showToast('附件已删除') } catch (error) { showToast(error instanceof Error ? error.message : '删除失败') }
}
async function beforeClose(action: string): Promise<boolean> {
  if (action === 'cancel') return true
  if (!reason.value.trim()) { showToast('请填写撤销原因'); return false }
  try { await closeDemand(demand.value.id, reason.value.trim()); await fetchDetail(); showToast('需求已撤销'); return true } catch { return false }
}
// ADMIN 打回（方案③）：原因必填；打回后需求转「待补充」，AI 会话重开并注入引述原因的播报
async function beforeReturn(action: string): Promise<boolean> {
  if (action === 'cancel') return true
  if (!returnReasonText.value.trim()) { showToast('请填写打回原因'); return false }
  try { await returnDemand(demand.value.id, returnReasonText.value.trim()); await fetchDetail(); showToast('已打回，等待提报人补充'); return true } catch { return false }
}
onMounted(fetchDetail)
</script>
<style scoped>
.page-loading { padding: 60px; text-align: center; }.detail-card { background: #fff; margin: 14px 12px; border-radius: 12px; padding: 18px 16px; }.number { font-size: 12px; color: #888; }.header h1 { font-size: 20px; line-height: 1.6; margin: 8px 0 14px; }.tags { display: flex; gap: 8px; flex-wrap: wrap; }.meta { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; font-size: 12px; color: #888; }h2 { font-size: 15px; margin: 0 0 12px; }.content { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.8; margin: 0; }.ext-row { display: grid; grid-template-columns: 92px 1fr; gap: 12px; margin: 12px 0; font-size: 13px; line-height: 1.7; }.ext-row strong { font-weight: 500; color: #888; min-width: 0; overflow-wrap: anywhere; }.ext-row span { min-width: 0; white-space: pre-wrap; overflow-wrap: anywhere; }.ext-row span small { display: block; color: #bbb; margin-top: 2px; }.zone-empty { margin: 0; font-size: 13px; color: #9ca3af; }.playback { padding: 4px 0; }.history-row { display: flex; font-size: 13px; line-height: 1.8; padding: 8px 0; }.history-row.from-user { justify-content: flex-end; }.history-row.from-assistant { justify-content: flex-start; }.history-row.from-system { justify-content: center; }.history-row .bubble { max-width: 82%; padding: 8px 12px; border-radius: 10px; background: #f4f6fa; }.history-row.from-user .bubble { background: #d8e6ff; }.history-row.from-system .bubble { background: transparent; padding: 2px 8px; }.bubble-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; font-size: 12px; color: #888; }.from-user .bubble-head { flex-direction: row-reverse; }.from-system .bubble-head { justify-content: center; }.bubble-head small { color: #999; }.history-row p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }.from-system .bubble p { font-size: 12px; color: #9ca3af; }.supp-title { font-size: 13px; color: #555; margin: 14px 0 4px; border-top: 1px dashed #e5e7eb; padding-top: 12px; }.supp-row { font-size: 13px; line-height: 1.8; margin: 8px 0; }.supp-row small { color: #999; display: block; }.supp-row p { margin: 2px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; }.ov-row { margin: 12px 0; }.ov-row strong { display: inline-block; font-size: 12px; font-weight: 600; color: #1f3a8a; background: #eef2ff; border-radius: 4px; padding: 2px 8px; margin-bottom: 4px; }.ov-row p { margin: 0; font-size: 14px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }.actions { display: flex; flex-direction: column; gap: 12px; padding-bottom: max(18px, env(safe-area-inset-bottom)); }
.return-card { border-left: 4px solid #f97316; background: #fff7ed; } .return-card h2 { color: #c2410c; } .return-card small { color: #b45309; }
.att-note { margin: 0 0 10px; font-size: 12px; color: #9ca3af; line-height: 1.6; }.att-cell { border-top: 1px solid #f1f2f4; }.att-row { display: flex; align-items: center; gap: 10px; padding: 10px 0; }.att-icon { font-size: 22px; color: #1f3a8a; flex-shrink: 0; }.att-meta { min-width: 0; display: flex; flex-direction: column; gap: 2px; }.att-meta strong { font-size: 14px; font-weight: 500; overflow-wrap: anywhere; }.att-meta small { font-size: 12px; color: #999; }.att-delete { height: 100%; }
.receipt { margin: 12px 12px 0; border-radius: 10px; }
/* 处理进度时间线：左圆点 + 竖线串联，最新一条在顶部 */
.flow-row { position: relative; display: flex; gap: 10px; padding: 10px 0 10px 2px; }
.flow-row:not(:last-child)::before { content: ''; position: absolute; left: 6px; top: 24px; bottom: -4px; width: 2px; background: #e5e7eb; }
.flow-dot { flex-shrink: 0; width: 10px; height: 10px; border-radius: 50%; background: #1f3a8a; margin-top: 4px; }
.flow-row:first-child .flow-dot { background: #16a34a; }
.flow-body { min-width: 0; }
.flow-line { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.flow-status { font-size: 12px; color: #1f3a8a; background: #eef2ff; border-radius: 4px; padding: 1px 6px; }
.flow-body small { color: #999; font-size: 12px; }
.flow-comment { margin: 4px 0 0; font-size: 12px; color: #606266; background: #f7f8fa; border-radius: 6px; padding: 6px 8px; white-space: pre-wrap; overflow-wrap: anywhere; }
.rate-row { display: flex; align-items: center; gap: 12px; padding: 10px 16px; }
.rate-label { font-size: 14px; color: #646566; width: 70px; flex-shrink: 0; }
</style>
