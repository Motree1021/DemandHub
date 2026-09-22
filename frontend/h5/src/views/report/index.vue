<template>
  <app-layout title="需求提报" active-tab="report">
    <template #right>
      <span class="draft-entry" @click="openDrafts">草稿箱{{ drafts.length ? `(${drafts.length})` : '' }}</span>
    </template>

    <!-- 用户行（对齐原型头部） -->
    <div class="user-row">
      <div class="avatar">{{ userStore.name.charAt(0) || '我' }}</div>
      <div>
        <div class="user-name">{{ userStore.name }}</div>
        <div class="user-meta"><span class="dot"></span>{{ userStore.userInfo?.orgName || '零售业务线' }} · 已登录</div>
      </div>
    </div>

    <!-- 类型选择（ActionSheet） -->
    <div class="form-card">
      <van-field
        :model-value="currentTypeName"
        label="需求类型"
        required
        readonly
        is-link
        placeholder="请选择需求类型"
        @click="typeSheetVisible = true"
      />
    </div>

    <!-- 公共字段 -->
    <div class="form-card">
      <van-field v-model="form.title" label="需求标题" required maxlength="100" placeholder="一句话描述你要解决的问题">
        <template #button>
          <van-icon name="volume-o" size="22" color="#1F3A8A" @click="onVoicePlaceholder" />
        </template>
      </van-field>
      <van-field
        v-model="form.content"
        label="需求描述"
        required
        type="textarea"
        rows="4"
        maxlength="2000"
        show-word-limit
        placeholder="请描述业务背景、使用场景、期望效果……"
      />
      <van-field label="紧急程度" required>
        <template #input>
          <div class="urgency-tags">
            <span
              v-for="u in urgencyOptions"
              :key="u.itemCode"
              class="urgency-tag"
              :class="{ selected: form.urgency === u.itemCode }"
              :style="form.urgency === u.itemCode ? selectedUrgencyStyle(u.itemCode) : {}"
              @click="form.urgency = u.itemCode"
            >{{ u.itemName }}</span>
          </div>
        </template>
      </van-field>
      <van-field
        :model-value="form.expectDeliveryAt ? fmtDate(form.expectDeliveryAt) : ''"
        label="期望交付时间"
        readonly
        is-link
        placeholder="选择日期"
        @click="calendarField = 'expectDeliveryAt'; calendarVisible = true"
      />
    </div>

    <!-- 科技需求扩展字段 -->
    <div v-if="form.demandTypeCode === 'TECH'" class="form-card">
      <div class="ext-title">科技需求信息</div>
      <van-field v-model="ext.relatedSystem" label="关联系统" placeholder="如：代销系统" />
      <van-field v-model="ext.relatedModule" label="关联模块" placeholder="如：数据看板" />
      <van-field v-model="ext.businessScenario" label="业务场景" type="textarea" rows="3" placeholder="什么人在什么场景下使用，解决什么问题" />
      <van-field v-model="ext.acceptanceCriteria" label="验收标准" type="textarea" rows="3" placeholder="怎样算完成，可量化的验收条件" />
    </div>

    <!-- 物料需求扩展字段 -->
    <div v-else-if="form.demandTypeCode === 'MATL'" class="form-card">
      <div class="ext-title">物料需求信息</div>
      <van-field v-model="ext.materialSubtype" label="物料子类" placeholder="如：宣传折页 / 易拉宝 / 海报" />
      <van-field label="数量">
        <template #input>
          <van-stepper v-model="ext.quantity" min="1" max="999999" />
        </template>
      </van-field>
      <van-field v-model="ext.usageScenario" label="使用场景" placeholder="如：四季度路演活动" />
      <van-field
        :model-value="ext.expectedArrivalAt ? fmtDate(ext.expectedArrivalAt) : ''"
        label="期望到位时间"
        readonly
        is-link
        placeholder="选择日期"
        @click="calendarField = 'expectedArrivalAt'; calendarVisible = true"
      />
    </div>

    <!-- 培训需求扩展字段 -->
    <div v-else-if="form.demandTypeCode === 'TRAIN'" class="form-card">
      <div class="ext-title">培训需求信息</div>
      <van-field v-model="ext.trainingSubtype" label="培训子类" placeholder="如：合规培训 / 产品培训 / 技能培训" />
      <van-field label="培训人数">
        <template #input>
          <van-stepper v-model="ext.traineeCount" min="1" max="99999" />
        </template>
      </van-field>
      <van-field v-model="ext.traineeObject" label="培训对象" placeholder="如：银行渠道新员工" />
      <van-field
        :model-value="ext.expectedCompleteAt ? fmtDate(ext.expectedCompleteAt) : ''"
        label="期望完成时间"
        readonly
        is-link
        placeholder="选择日期"
        @click="calendarField = 'expectedCompleteAt'; calendarVisible = true"
      />
    </div>

    <!-- 自定义类型提示 -->
    <van-notice-bar
      v-else-if="!isBuiltinType"
      left-icon="info-o"
      text="该类型无扩展字段，请在需求描述中写清业务背景与期望效果"
      class="ext-notice"
    />

    <!-- 代办提报 -->
    <div class="form-card">
      <van-field label="代办提报">
        <template #input>
          <van-switch v-model="proxyMode" size="22" />
        </template>
      </van-field>
      <template v-if="proxyMode">
        <user-picker v-model="form.actualDemanderId" label="实际需求人" placeholder="选择实际需求人" />
        <div class="proxy-tip">提交后提报人为你，实际需求人为所选同事；对方可在「我的需求」看到该需求</div>
      </template>
    </div>

    <!-- 附件（拍照/相册，DRAFT 暂存） -->
    <div class="form-card">
      <div class="att-label">附件</div>
      <div class="att-grid">
        <div v-for="item in attachments" :key="item.att.id" class="att-thumb" @click="onPreview(item)">
          <img v-if="isImage(item.att)" :src="item.url" alt="附件缩略图" />
          <div v-else class="att-file">
            <van-icon name="description" size="24" color="#1F3A8A" />
            <span class="att-file-name">{{ item.att.fileName }}</span>
          </div>
          <van-icon name="cross" class="att-del" @click.stop="onRemoveAttachment(item)" />
        </div>
        <van-uploader
          v-model="uploaderFiles"
          multiple
          accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.zip"
          :after-read="onUpload"
          :max-count="9"
        >
          <div class="att-add">
            <van-icon v-if="!uploading" name="photograph" size="26" color="#999" />
            <van-loading v-else size="22" />
            <span class="att-add-text">{{ uploading ? `${uploadPercent}%` : '拍照/附件' }}</span>
          </div>
        </van-uploader>
      </div>
      <div class="att-tip">支持拍照、相册或文件附件（图片/PDF/Office），单文件 ≤ 50MB</div>
    </div>

    <!-- 提交区（触控高度 ≥44px） -->
    <div class="submit-bar">
      <van-button plain block :loading="savingDraft" class="btn-draft" @click="onSaveDraft">暂存草稿</van-button>
      <van-button type="primary" block :loading="submitting" class="btn-submit" @click="onSubmit">提交需求</van-button>
    </div>

    <!-- 类型选择 ActionSheet -->
    <van-action-sheet
      v-model:show="typeSheetVisible"
      :actions="typeActions"
      cancel-text="取消"
      @select="onTypeSelect"
    />

    <!-- 日期选择 -->
    <van-calendar
      v-model:show="calendarVisible"
      :min-date="minDate"
      :default-date="calendarDefault"
      @confirm="onDateConfirm"
    />

    <!-- 草稿箱 -->
    <van-popup v-model:show="draftVisible" position="bottom" round :style="{ height: '60%' }">
      <div class="draft-panel">
        <div class="draft-title">我的草稿</div>
        <div class="draft-list">
          <van-empty v-if="!drafts.length" description="暂无草稿" />
          <van-cell
            v-for="d in drafts"
            :key="d.id"
            :title="draftTitle(d)"
            :label="`更新于 ${fmtTime(d.updatedAt)}`"
            clickable
            @click="onLoadDraft(d)"
          >
            <template #right-icon>
              <van-icon name="delete-o" color="#ff4757" size="18" @click.stop="onDeleteDraft(d)" />
            </template>
          </van-cell>
        </div>
      </div>
    </van-popup>
  </app-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast, showConfirmDialog, showImagePreview, type UploaderFileListItem } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import UserPicker from '@/components/UserPicker.vue'
import {
  listDictItems,
  saveDraft,
  listDrafts,
  deleteDraft,
  submitDemand,
  uploadAttachment,
  listAttachments,
  deleteAttachment,
  previewAttachmentUrl,
  type AttachmentItem,
  type DraftItem,
  type DictItem
} from '@/api/demand'
import { listActiveTypes, type DemandTypeItem } from '@/api/directory'
import { useUserStore } from '@/store/user'
import { fmtTime, fmtDate, typeMeta, urgencyMeta } from '@/utils/format'

const router = useRouter()
const userStore = useUserStore()

const BUILTIN = ['TECH', 'MATL', 'TRAIN']

interface ExtForm {
  relatedSystem?: string
  relatedModule?: string
  businessScenario?: string
  acceptanceCriteria?: string
  materialSubtype?: string
  usageScenario?: string
  quantity?: number
  expectedArrivalAt?: string
  trainingSubtype?: string
  traineeObject?: string
  traineeCount?: number
  expectedCompleteAt?: string
}

const emptyForm = () => ({
  title: '',
  content: '',
  demandTypeCode: 'TECH',
  urgency: 'NORMAL',
  expectDeliveryAt: undefined as string | undefined,
  actualDemanderId: null as number | null
})

const form = reactive(emptyForm())
const ext = reactive<ExtForm>({})
const proxyMode = ref(false)
const attachments = ref<{ att: AttachmentItem; url: string }[]>([])
const drafts = ref<DraftItem[]>([])
const draftVisible = ref(false)
const currentDraftId = ref<number | null>(null)
const typeList = ref<DemandTypeItem[]>([])
const urgencyOptions = ref<DictItem[]>([])
const typeSheetVisible = ref(false)
const calendarVisible = ref(false)
const calendarField = ref<'expectDeliveryAt' | 'expectedArrivalAt' | 'expectedCompleteAt'>('expectDeliveryAt')
const uploaderFiles = ref<UploaderFileListItem[]>([])
const uploading = ref(false)
const uploadPercent = ref(0)
const savingDraft = ref(false)
const submitting = ref(false)

const minDate = new Date()

const isBuiltinType = computed(() => BUILTIN.includes(form.demandTypeCode))

const currentTypeName = computed(() => {
  const t = typeList.value.find((x) => x.typeCode === form.demandTypeCode)
  if (!t) {
    return '请选择需求类型'
  }
  return `${typeMeta(t.typeCode).icon} ${t.typeName}`
})

const typeActions = computed(() =>
  typeList.value.map((t) => ({
    name: `${typeMeta(t.typeCode).icon} ${t.typeName}`,
    value: t.typeCode,
    color: t.typeCode === form.demandTypeCode ? '#1F3A8A' : undefined
  }))
)

const calendarDefault = computed(() => {
  const map: Record<string, string | undefined> = {
    expectDeliveryAt: form.expectDeliveryAt,
    expectedArrivalAt: ext.expectedArrivalAt,
    expectedCompleteAt: ext.expectedCompleteAt
  }
  const v = map[calendarField.value]
  return v ? new Date(v.slice(0, 10)) : new Date()
})

function selectedUrgencyStyle(code: string) {
  const m = urgencyMeta(code)
  return { background: m.color === '#ffffff' ? '#ff4757' : m.color, borderColor: m.color, color: '#fff' }
}

function onTypeSelect(action: { value?: string }) {
  if (action.value && action.value !== form.demandTypeCode) {
    form.demandTypeCode = action.value
    // 切换类型清空扩展字段，避免串字段
    Object.keys(ext).forEach((k) => delete (ext as Record<string, unknown>)[k])
    // stepper 无空态，给数字字段默认值保证「所见即所交」
    if (action.value === 'MATL') {
      ext.quantity = 1
    } else if (action.value === 'TRAIN') {
      ext.traineeCount = 1
    }
  }
  typeSheetVisible.value = false
}

function onVoicePlaceholder() {
  showToast('语音输入二期接入企微语音消息，敬请期待')
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

function onDateConfirm(d: Date) {
  const ymd = `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T00:00:00`
  if (calendarField.value === 'expectDeliveryAt') {
    form.expectDeliveryAt = ymd
  } else {
    ext[calendarField.value] = ymd
  }
  calendarVisible.value = false
}

function currentExt(): Record<string, unknown> {
  const cleaned: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(ext)) {
    if (v !== undefined && v !== null && v !== '') {
      cleaned[k] = v
    }
  }
  return cleaned
}

function isImage(att: AttachmentItem): boolean {
  return (att.mimeType || '').startsWith('image/')
}

async function onUpload(items: UploaderFileListItem | UploaderFileListItem[]) {
  const files = (Array.isArray(items) ? items : [items]).filter((it): it is UploaderFileListItem & { file: File } => !!it.file)
  uploading.value = true
  uploadPercent.value = 0
  try {
    for (const item of files) {
      const file = item.file
      if (file.size > 50 * 1024 * 1024) {
        showToast(`${file.name} 超过 50MB，已跳过`)
        continue
      }
      // 暂存附件挂在 DRAFT 业务下（bizId 用当前用户 ID 占位），提交时由后端 rebind 到需求
      const att = await uploadAttachment('DRAFT', userStore.userInfo?.id || 0, file, (p) => (uploadPercent.value = p))
      const url = isImage(att) ? await previewAttachmentUrl(att.id) : ''
      attachments.value.push({ att, url })
    }
  } finally {
    uploading.value = false
    // 清空 uploader 内部列表，缩略图由自渲染网格负责
    uploaderFiles.value = []
  }
}

function onPreview(item: { att: AttachmentItem; url: string }) {
  if (isImage(item.att) && item.url) {
    showImagePreview({ images: [item.url], closeable: true })
  }
}

async function onRemoveAttachment(item: { att: AttachmentItem; url: string }) {
  await deleteAttachment(item.att.id)
  if (item.url) {
    window.URL.revokeObjectURL(item.url)
  }
  attachments.value = attachments.value.filter((a) => a.att.id !== item.att.id)
}

function buildDraftPayload(): string {
  return JSON.stringify({
    ...form,
    ext: currentExt(),
    proxyMode: proxyMode.value,
    attachmentIds: attachments.value.map((a) => a.att.id)
  })
}

async function onSaveDraft() {
  if (!form.title && !form.content) {
    showToast('草稿至少需要标题或描述')
    return
  }
  savingDraft.value = true
  try {
    const saved = await saveDraft({
      id: currentDraftId.value || undefined,
      formPayload: buildDraftPayload()
    })
    currentDraftId.value = saved.id
    showSuccessToast('草稿已保存')
    loadDrafts()
  } finally {
    savingDraft.value = false
  }
}

async function loadDrafts() {
  drafts.value = await listDrafts()
}

function openDrafts() {
  draftVisible.value = true
  loadDrafts()
}

function draftTitle(d: DraftItem): string {
  try {
    const payload = JSON.parse(d.formPayload)
    return payload.title || '（无标题草稿）'
  } catch {
    return '（无标题草稿）'
  }
}

async function onLoadDraft(d: DraftItem) {
  try {
    const payload = JSON.parse(d.formPayload)
    Object.assign(form, emptyForm(), {
      title: payload.title || '',
      content: payload.content || '',
      demandTypeCode: payload.demandTypeCode || 'TECH',
      urgency: payload.urgency || 'NORMAL',
      expectDeliveryAt: payload.expectDeliveryAt,
      actualDemanderId: payload.actualDemanderId || null
    })
    Object.keys(ext).forEach((k) => delete (ext as Record<string, unknown>)[k])
    Object.assign(ext, payload.ext || {})
    proxyMode.value = !!payload.proxyMode
    currentDraftId.value = d.id
    // 草稿附件回显：从本人 DRAFT 暂存池按 payload.attachmentIds 过滤
    attachments.value.forEach((a) => a.url && window.URL.revokeObjectURL(a.url))
    attachments.value = []
    const ids: number[] = payload.attachmentIds || []
    if (ids.length && userStore.userInfo?.id) {
      const pool = await listAttachments('DRAFT', userStore.userInfo.id)
      for (const att of pool.filter((a) => ids.includes(a.id))) {
        const url = isImage(att) ? await previewAttachmentUrl(att.id) : ''
        attachments.value.push({ att, url })
      }
    }
    draftVisible.value = false
    showSuccessToast('草稿已载入，可继续编辑')
  } catch {
    showToast('草稿内容解析失败')
  }
}

async function onDeleteDraft(d: DraftItem) {
  await showConfirmDialog({ title: '提示', message: '确认删除该草稿？' })
  await deleteDraft(d.id)
  if (currentDraftId.value === d.id) {
    currentDraftId.value = null
  }
  loadDrafts()
}

function validate(): boolean {
  if (!form.title.trim()) {
    showToast('请输入需求标题')
    return false
  }
  if (!form.content.trim()) {
    showToast('请输入需求描述')
    return false
  }
  if (!form.urgency) {
    showToast('请选择紧急程度')
    return false
  }
  if (proxyMode.value && !form.actualDemanderId) {
    showToast('代办提报请选择实际需求人')
    return false
  }
  return true
}

async function onSubmit() {
  if (!validate()) {
    return
  }
  submitting.value = true
  try {
    const demand = await submitDemand({
      draftId: currentDraftId.value || undefined,
      title: form.title.trim(),
      content: form.content,
      demandTypeCode: form.demandTypeCode,
      urgency: form.urgency,
      expectDeliveryAt: form.expectDeliveryAt,
      actualDemanderId: proxyMode.value ? form.actualDemanderId || undefined : undefined,
      ext: currentExt(),
      attachmentIds: attachments.value.map((a) => a.att.id)
    })
    showSuccessToast(`需求 ${demand.demandNo} 提交成功`)
    router.replace(`/demand/${demand.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  typeList.value = await listActiveTypes()
  if (typeList.value.length && !typeList.value.some((t) => t.typeCode === form.demandTypeCode)) {
    form.demandTypeCode = typeList.value[0].typeCode
  }
  urgencyOptions.value = await listDictItems('URGENCY')
  loadDrafts()
})
</script>

<style scoped>
/* 用户行（深蓝头部下沿，对齐原型） */
.user-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px 26px;
  background: linear-gradient(135deg, #1F3A8A 0%, #2F56B8 100%);
  color: #fff;
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}

.user-name {
  font-size: 16px;
  font-weight: 600;
}

.user-meta {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.75);
  margin-top: 3px;
}

.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #4ade80;
  margin-right: 4px;
}

.draft-entry {
  font-size: 13px;
  color: #fff;
}

/* 白色圆角表单卡片 */
.form-card {
  background: #fff;
  border-radius: 14px;
  margin: 12px 12px 0;
  padding: 4px 0;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.form-card:first-of-type {
  margin-top: -14px;
  position: relative;
  z-index: 2;
}

.ext-title {
  font-size: 13px;
  font-weight: 600;
  color: #1F3A8A;
  padding: 12px 16px 4px;
  border-left: 3px solid #1F3A8A;
  margin: 8px 0 4px 12px;
  padding-left: 8px;
}

.ext-notice {
  margin: 12px 12px 0;
  border-radius: 10px;
}

/* 紧急程度标签选择 */
.urgency-tags {
  display: flex;
  gap: 8px;
}

.urgency-tag {
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid #ddd;
  font-size: 13px;
  color: #666;
  min-height: 32px;
  display: inline-flex;
  align-items: center;
}

.urgency-tag.selected {
  background: #1F3A8A;
  color: #fff;
  border-color: #1F3A8A;
}

.proxy-tip {
  font-size: 11px;
  color: #999;
  padding: 0 16px 12px;
}

/* 附件网格 */
.att-label {
  font-size: 13px;
  color: #666;
  padding: 12px 16px 8px;
}

.att-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 0 16px 4px;
}

.att-thumb {
  width: 64px;
  height: 64px;
  border-radius: 8px;
  overflow: hidden;
  position: relative;
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

.att-del {
  position: absolute;
  top: 2px;
  right: 2px;
  background: rgba(0, 0, 0, 0.5);
  color: #fff;
  border-radius: 50%;
  padding: 2px;
  font-size: 10px;
}

.att-add {
  width: 64px;
  height: 64px;
  border: 1px dashed #ccc;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #999;
}

.att-add-text {
  font-size: 10px;
  margin-top: 2px;
}

.att-tip {
  font-size: 11px;
  color: #999;
  padding: 6px 16px 12px;
}

/* 提交区 */
.submit-bar {
  display: flex;
  gap: 12px;
  padding: 16px;
}

.submit-bar .van-button {
  height: 46px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
}

.btn-draft {
  flex: 1;
}

.btn-submit {
  flex: 2;
}

/* 草稿箱 */
.draft-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.draft-title {
  text-align: center;
  font-size: 16px;
  font-weight: 600;
  padding: 16px 0 8px;
}

.draft-list {
  flex: 1;
  overflow-y: auto;
}
</style>
