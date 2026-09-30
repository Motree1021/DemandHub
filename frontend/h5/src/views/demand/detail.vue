<template>
  <app-layout title="需求详情" show-back>
    <van-loading v-if="!detail" class="page-loading" size="28" vertical>加载中...</van-loading>

    <template v-else>
      <!-- 深蓝头部区（对齐原型⑤） -->
      <div class="hero">
        <div class="hero-no">{{ d.demandNo }}</div>
        <div class="hero-title">{{ d.title }}</div>
        <div class="hero-tags">
          <span class="tag" :style="tagStyle(typeMeta(d.demandTypeCode))">{{ typeLabel(d.demandTypeCode, detail.typeName) }}</span>
          <span class="tag" :style="tagStyle(statusMeta(d.status))">{{ statusLabel(d.status) }}</span>
          <span class="tag" :style="tagStyle(urgencyMeta(d.urgency))">{{ urgencyLabel(d.urgency) }}</span>
          <span v-if="d.onHold === 1" class="tag" style="background:#fef3c7;color:#b45309">已挂起{{ detail.holdDays != null ? ` ${detail.holdDays}天` : '' }}</span>
        </div>
      </div>

      <!-- 基本信息折叠卡片 -->
      <van-collapse v-model="collapseActive" class="card">
        <van-collapse-item title="基本信息" name="base">
          <div class="base-content">{{ d.content }}</div>
          <div class="base-rows">
            <div class="base-row"><span class="base-label">提报人</span><span>{{ detail.submitterName || '-' }}<template v-if="detail.actualDemanderName">（代 {{ detail.actualDemanderName }} 提报）</template></span></div>
            <div class="base-row"><span class="base-label">期望交付</span><span>{{ d.expectDeliveryAt ? fmtDate(d.expectDeliveryAt) : '-' }}</span></div>
            <div class="base-row"><span class="base-label">承接组织</span><span>{{ detail.assigneeOrgName || '待分派' }}</span></div>
            <div class="base-row"><span class="base-label">当前处理人</span><span>{{ detail.assigneeUserName || '-' }}</span></div>
            <div class="base-row"><span class="base-label">提交时间</span><span>{{ fmtTime(d.submittedAt) }}</span></div>
            <template v-if="detail.ext">
              <div v-for="(label, key) in extEntries" :key="key" class="base-row">
                <span class="base-label">{{ label }}</span><span>{{ extValue(key) }}</span>
              </div>
            </template>
            <div v-if="d.onHold === 1 && d.holdReason" class="base-row"><span class="base-label">挂起原因</span><span>{{ d.holdReason }}</span></div>
            <div v-if="d.closeReason" class="base-row"><span class="base-label">关闭原因</span><span>{{ d.closeReason }}</span></div>
            <div v-if="d.qualityScore != null" class="base-row"><span class="base-label">质量评分</span><span>{{ d.qualityScore }} 分</span></div>
            <div v-if="d.satisfactionScore != null" class="base-row"><span class="base-label">满意度</span><span>{{ d.satisfactionScore }} 分</span></div>
          </div>
        </van-collapse-item>
      </van-collapse>

      <!-- 附件区 -->
      <div v-if="detail.attachments.length" class="card">
        <div class="card-title">附件（{{ detail.attachments.length }}）</div>
        <div class="att-grid">
          <div v-for="(att, i) in detail.attachments" :key="att.id" class="att-thumb" @click="onPreviewAttachment(att, i)">
            <img v-if="isImage(att) && attUrls[att.id]" :src="attUrls[att.id]" alt="附件" />
            <div v-else class="att-file">
              <van-icon name="description" size="24" color="#1F3A8A" />
              <span class="att-file-name">{{ att.fileName }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 处理进度时间线（竖版，对齐原型） -->
      <div class="card">
        <div class="card-title">处理进度</div>
        <div class="timeline">
          <div v-for="(t, i) in transitions" :key="t.id" class="tl-item">
            <div class="tl-dot" :class="{ latest: i === 0 }"></div>
            <div v-if="i < transitions.length - 1" class="tl-line"></div>
            <div class="tl-content">
              <div class="tl-status" :class="{ old: i > 0 }">
                {{ t.fromStatus ? statusLabel(t.fromStatus) : '开始' }} → {{ statusLabel(t.toStatus) }}
              </div>
              <div class="tl-time">{{ fmtTime(t.createdAt) }} · {{ t.operatorSnapshot || userName(t.operatorId) }} · {{ eventLabel(t.action) }}</div>
              <div v-if="t.comment" class="tl-desc">意见：{{ t.comment }}</div>
            </div>
          </div>
          <van-empty v-if="!transitions.length" description="暂无流转记录" :image-size="60" />
        </div>
      </div>

      <!-- 评论区 -->
      <div class="card">
        <div class="card-title">评论（{{ comments.length }}）</div>
        <div v-for="c in comments" :key="c.id" class="comment-item">
          <div class="comment-avatar">{{ userName(c.authorId).charAt(0) }}</div>
          <div class="comment-main">
            <div class="comment-head">
              <span class="comment-author">{{ userName(c.authorId) }}</span>
              <span class="comment-time">{{ fmtTime(c.createdAt) }}</span>
            </div>
            <div class="comment-content">{{ c.content }}</div>
            <div v-if="mentionNames(c).length" class="comment-mentions">提醒：{{ mentionNames(c).join('、') }}</div>
          </div>
        </div>
        <van-empty v-if="!comments.length" description="暂无评论" :image-size="60" />
      </div>

      <!-- 底部固定区：操作栏 + 评论输入框 -->
      <div v-if="actionButtons.length || hasAction('COMMENT')" class="bottom-bar">
        <div v-if="actionButtons.length" class="action-row">
          <van-button
            v-for="btn in actionButtons"
            :key="btn.key"
            :type="btn.color"
            size="normal"
            class="action-btn"
            :loading="acting === btn.key"
            @click="onAction(btn)"
          >{{ btn.label }}</van-button>
        </div>
        <div v-if="hasAction('COMMENT')" class="comment-row">
          <van-field v-model="commentInput" class="comment-input" placeholder="发表评论，可 @同事 提醒" />
          <span class="mention-btn" :class="{ active: mentionIds.length }" @click="mentionVisible = true">@</span>
          <van-button type="primary" size="normal" class="send-btn" :disabled="!commentInput.trim()" :loading="commenting" @click="onAddComment">发送</van-button>
        </div>
        <div v-if="mentionIds.length" class="mention-chips">
          <span v-for="id in mentionIds" :key="id" class="mention-chip" @click="removeMention(id)">@{{ userName(id) }} ×</span>
        </div>
      </div>

      <!-- 意见输入弹窗（撤销/退回/关闭/挂起/受理/分派） -->
      <van-dialog
        v-model:show="dlg.visible"
        :title="dlg.title"
        show-cancel-button
        :before-close="onDialogBeforeClose"
      >
        <div class="dlg-body">
          <user-picker
            v-if="dlg.needUser"
            v-model="dlg.userId"
            label="处理人"
            placeholder="选择处理人"
          />
          <van-field
            v-model="dlg.comment"
            type="textarea"
            rows="3"
            maxlength="500"
            :placeholder="dlg.placeholder"
          />
        </div>
      </van-dialog>

      <!-- @人选择 -->
      <user-picker v-model="mentionIdsProxy" multiple hide-field v-model:visible="mentionVisible" />
    </template>
  </app-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showSuccessToast, showConfirmDialog, showImagePreview, showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import UserPicker from '@/components/UserPicker.vue'
import {
  getDemand,
  getTransitions,
  listComments,
  addComment,
  withdrawDemand,
  resubmitDemand,
  acceptDemand,
  returnDemand,
  closeDemand,
  assignDemand,
  claimDemand,
  startDemand,
  holdDemand,
  resumeDemand,
  submitAcceptance,
  previewAttachmentUrl,
  listDictItems,
  type DemandDetail,
  type TransitionLog,
  type CommentItem,
  type AttachmentItem,
  type DictItem
} from '@/api/demand'
import { listAllUsers, type UserSnapshotVO } from '@/api/directory'
import {
  statusLabel,
  statusMeta,
  typeLabel,
  typeMeta,
  urgencyLabel,
  urgencyMeta,
  eventLabel,
  fmtTime,
  fmtDate,
  EXT_FIELD_LABELS,
  type ColorMeta
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const demandId = Number(route.params.id)

const detail = ref<DemandDetail | null>(null)
const transitions = ref<TransitionLog[]>([])
const comments = ref<CommentItem[]>([])
const allUsers = ref<UserSnapshotVO[]>([])
const subtypeOptions = ref<DictItem[]>([])
const attUrls = ref<Record<number, string>>({})
const collapseActive = ref(['base'])
const commentInput = ref('')
const commenting = ref(false)
const mentionIds = ref<number[]>([])
const mentionVisible = ref(false)
const acting = ref('')

const d = computed(() => detail.value!.demand)

interface ActionDef {
  key: string
  label: string
  color: 'primary' | 'warning' | 'danger'
  kind: 'confirm' | 'dialog' | 'nav'
  confirmText?: string
  required?: boolean
  needUser?: boolean
  placeholder?: string
}

/** 移动端主操作（其余动作 PC 端处理）；顺序即展示顺序 */
const ACTION_DEFS: ActionDef[] = [
  { key: 'ACCEPTANCE_REVIEW', label: '验收评审', color: 'primary', kind: 'nav' },
  { key: 'ACCEPT', label: '受理', color: 'primary', kind: 'dialog', placeholder: '受理意见（选填）' },
  { key: 'ASSIGN', label: '分派', color: 'primary', kind: 'dialog', needUser: true, placeholder: '分派意见（选填）' },
  { key: 'CLAIM', label: '领取', color: 'primary', kind: 'confirm', confirmText: '确认领取该需求？' },
  { key: 'START', label: '开始处理', color: 'primary', kind: 'confirm', confirmText: '确认开始处理该需求？' },
  { key: 'SUBMIT_ACCEPTANCE', label: '提交验收', color: 'primary', kind: 'confirm', confirmText: '确认交付并提交验收？提报人将收到验收邀请。' },
  { key: 'RESUBMIT', label: '重新提交', color: 'primary', kind: 'confirm', confirmText: '将以原内容重新提交，确认？' },
  { key: 'RESUME', label: '恢复', color: 'primary', kind: 'confirm', confirmText: '确认恢复处理？' },
  { key: 'RETURN', label: '退回补充', color: 'warning', kind: 'dialog', required: true, placeholder: '退回原因（必填）' },
  { key: 'HOLD', label: '挂起', color: 'warning', kind: 'dialog', required: true, placeholder: '挂起原因（必填）' },
  { key: 'WITHDRAW', label: '撤销', color: 'danger', kind: 'dialog', required: true, placeholder: '撤销原因（必填）' },
  { key: 'CLOSE', label: '关闭', color: 'danger', kind: 'dialog', required: true, placeholder: '关闭原因（必填）' }
]

const actionButtons = computed(() => ACTION_DEFS.filter((a) => hasAction(a.key)))

const dlg = reactive({
  visible: false,
  action: '',
  title: '',
  placeholder: '',
  required: false,
  needUser: false,
  comment: '',
  userId: null as number | null
})

const mentionIdsProxy = computed({
  get: () => mentionIds.value,
  set: (v) => {
    mentionIds.value = Array.isArray(v) ? v : v != null ? [v] : []
  }
})

const userMap = computed(() => new Map(allUsers.value.map((u) => [u.id, u.name])))

const extEntries = computed(() => {
  const ext = detail.value?.ext
  if (!ext) {
    return {}
  }
  const entries: Record<string, string> = {}
  for (const [k, label] of Object.entries(EXT_FIELD_LABELS)) {
    const v = (ext as Record<string, unknown>)[k]
    if (v !== undefined && v !== null && v !== '') {
      entries[k] = label
    }
  }
  return entries
})

function extValue(key: string): string {
  const v = (detail.value!.ext as Record<string, unknown>)[key]
  if (key === 'techSubtype') {
    // 子类存字典 itemCode，展示 itemName；未命中（历史/自定义）原样展示
    return subtypeOptions.value.find((s) => s.itemCode === v)?.itemName || String(v)
  }
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) {
    return fmtDate(v)
  }
  return String(v)
}

function tagStyle(m: ColorMeta) {
  return { background: m.bg, color: m.color }
}

function hasAction(action: string): boolean {
  return detail.value?.availableActions?.includes(action) ?? false
}

function userName(id: number | null | undefined): string {
  if (id == null) {
    return '-'
  }
  return userMap.value.get(id) || `#${id}`
}

function isImage(att: AttachmentItem): boolean {
  return (att.mimeType || '').startsWith('image/')
}

function mentionNames(c: CommentItem): string[] {
  if (!c.mentionedUserIds) {
    return []
  }
  return c.mentionedUserIds
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((n) => !Number.isNaN(n))
    .map((id) => userName(id))
}

function removeMention(id: number) {
  mentionIds.value = mentionIds.value.filter((x) => x !== id)
}

async function onPreviewAttachment(att: AttachmentItem, _index: number) {
  if (!isImage(att)) {
    showToast('该文件类型暂不支持预览，请在 PC 端下载')
    return
  }
  const images = detail.value!.attachments.filter(isImage).map((a) => attUrls.value[a.id]).filter(Boolean)
  const start = detail.value!.attachments.filter(isImage).findIndex((a) => a.id === att.id)
  showImagePreview({ images, startPosition: Math.max(start, 0), closeable: true })
}

function onAction(btn: ActionDef) {
  if (btn.kind === 'nav') {
    router.push(`/demand/${demandId}/acceptance`)
    return
  }
  if (btn.kind === 'confirm') {
    showConfirmDialog({ title: btn.label, message: btn.confirmText }).then(() => runAction(btn.key)).catch(() => {})
    return
  }
  dlg.visible = true
  dlg.action = btn.key
  dlg.title = btn.label
  dlg.placeholder = btn.placeholder || '请输入意见'
  dlg.required = !!btn.required
  dlg.needUser = !!btn.needUser
  dlg.comment = ''
  dlg.userId = null
}

function onDialogBeforeClose(action: string): boolean {
  if (action !== 'confirm') {
    return true
  }
  if (dlg.required && !dlg.comment.trim()) {
    showToast(dlg.placeholder)
    return false
  }
  if (dlg.needUser && !dlg.userId) {
    showToast('请选择处理人')
    return false
  }
  runAction(dlg.action, dlg.comment.trim(), dlg.userId)
  return true
}

async function runAction(action: string, comment = '', userId: number | null = null) {
  acting.value = action
  try {
    switch (action) {
      case 'WITHDRAW':
        await withdrawDemand(demandId, comment)
        break
      case 'RESUBMIT':
        await resubmitDemand(demandId, {})
        break
      case 'ACCEPT':
        await acceptDemand(demandId, comment || undefined)
        break
      case 'RETURN':
        await returnDemand(demandId, comment)
        break
      case 'CLOSE':
        await closeDemand(demandId, comment)
        break
      case 'ASSIGN':
        await assignDemand(demandId, userId!, comment || undefined)
        break
      case 'CLAIM':
        await claimDemand(demandId)
        break
      case 'START':
        await startDemand(demandId)
        break
      case 'HOLD':
        await holdDemand(demandId, comment)
        break
      case 'RESUME':
        await resumeDemand(demandId)
        break
      case 'SUBMIT_ACCEPTANCE':
        await submitAcceptance(demandId)
        break
    }
    showSuccessToast('操作成功')
    await reload()
  } finally {
    acting.value = ''
  }
}

async function onAddComment() {
  if (!commentInput.value.trim()) {
    return
  }
  commenting.value = true
  try {
    await addComment({
      demandId,
      content: commentInput.value.trim(),
      mentionedUserIds: mentionIds.value.length ? mentionIds.value : undefined
    })
    commentInput.value = ''
    mentionIds.value = []
    comments.value = await listComments(demandId)
    showSuccessToast('已发表')
  } finally {
    commenting.value = false
  }
}

async function reload() {
  const [d, t, c] = await Promise.all([getDemand(demandId), getTransitions(demandId), listComments(demandId)])
  detail.value = d
  // 时间线最新在上（后端按时间升序返回，id 自增即时间序）
  transitions.value = [...t].sort((a, b) => b.id - a.id)
  comments.value = c
  // 图片附件拉 blob 转 objectURL
  for (const att of d.attachments) {
    if (isImage(att) && !attUrls.value[att.id]) {
      attUrls.value[att.id] = await previewAttachmentUrl(att.id)
    }
  }
}

onMounted(async () => {
  const [users, subtypes] = await Promise.all([listAllUsers(), listDictItems('TECH_SUBTYPE')])
  allUsers.value = users
  subtypeOptions.value = subtypes
  await reload()
})
</script>

<style scoped>
.page-loading {
  display: flex;
  justify-content: center;
  padding-top: 80px;
}

/* 深蓝头部区 */
.hero {
  background: linear-gradient(135deg, #1F3A8A 0%, #2F56B8 100%);
  color: #fff;
  padding: 14px 16px 26px;
}

.hero-no {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
}

.hero-title {
  font-size: 17px;
  font-weight: 600;
  margin-top: 6px;
}

.hero-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
}

/* 白色卡片 */
.card {
  background: #fff;
  border-radius: 14px;
  margin: 12px 12px 0;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.card:first-of-type {
  margin-top: -14px;
  position: relative;
  z-index: 2;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  border-left: 3px solid #1F3A8A;
  padding-left: 8px;
  margin: 14px 14px 10px;
}

/* 基本信息 */
.base-content {
  font-size: 13px;
  color: #555;
  line-height: 1.6;
  white-space: pre-wrap;
  padding: 0 16px 10px;
}

.base-rows {
  border-top: 1px solid #f0f0f0;
  padding: 10px 16px 6px;
}

.base-row {
  display: flex;
  font-size: 12px;
  color: #333;
  margin-bottom: 8px;
}

.base-label {
  color: #888;
  width: 76px;
  flex-shrink: 0;
}

/* 附件 */
.att-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 14px 14px;
}

.att-thumb {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  overflow: hidden;
  background: #eef3fb;
}

.att-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.att-file {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #1F3A8A;
  padding: 4px;
}

.att-file-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 时间线（对齐原型竖版） */
.timeline {
  padding: 4px 16px 14px;
}

.tl-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 16px;
}

.tl-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #d1d5db;
  margin-top: 4px;
  flex-shrink: 0;
  z-index: 1;
}

.tl-dot.latest {
  background: #1F3A8A;
}

.tl-line {
  position: absolute;
  left: 4px;
  top: 16px;
  width: 2px;
  height: calc(100% - 10px);
  background: #e5e7eb;
}

.tl-content {
  flex: 1;
  min-width: 0;
}

.tl-status {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.tl-status.old {
  color: #888;
}

.tl-time {
  font-size: 11px;
  color: #999;
  margin-top: 2px;
}

.tl-desc {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
  word-break: break-all;
}

/* 评论 */
.comment-item {
  display: flex;
  gap: 10px;
  padding: 0 14px 12px;
}

.comment-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #eef3fb;
  color: #1F3A8A;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.comment-main {
  flex: 1;
  min-width: 0;
}

.comment-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.comment-author {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.comment-time {
  font-size: 11px;
  color: #999;
}

.comment-content {
  font-size: 13px;
  color: #555;
  margin-top: 4px;
  word-break: break-all;
  white-space: pre-wrap;
}

.comment-mentions {
  font-size: 11px;
  color: #1F3A8A;
  margin-top: 4px;
}

/* 底部固定区 */
.bottom-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
  border-top: 1px solid #eee;
  padding: 8px 12px calc(8px + env(safe-area-inset-bottom));
  z-index: 10;
}

.action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.action-btn {
  flex: 1 1 30%;
  min-width: 96px;
  min-height: 44px;
  border-radius: 8px;
}

.comment-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comment-input {
  flex: 1;
  background: #f5f6f8;
  border-radius: 20px;
  padding: 8px 14px;
}

.mention-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #eef3fb;
  color: #1F3A8A;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.mention-btn.active {
  background: #1F3A8A;
  color: #fff;
}

.send-btn {
  min-height: 36px;
  border-radius: 18px;
  flex-shrink: 0;
}

.mention-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.mention-chip {
  font-size: 11px;
  background: #eef3fb;
  color: #1F3A8A;
  border-radius: 10px;
  padding: 2px 8px;
}

.dlg-body {
  padding: 8px 16px 16px;
}

/* 给底部固定栏预留空间（操作行 wrap 两行 + 评论行 + 安全区） */
:deep(.app-body) {
  padding-bottom: calc(190px + env(safe-area-inset-bottom)) !important;
}
</style>
