<template>
  <div class="report-page">
    <el-row :gutter="16">
      <el-col :span="17">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>提报需求</span>
              <el-button text type="primary" @click="draftDrawer = true">
                草稿箱{{ drafts.length ? `（${drafts.length}）` : '' }}
              </el-button>
            </div>
          </template>

          <!-- 类型选择 tab -->
          <el-tabs v-model="form.demandTypeCode" class="type-tabs" @tab-change="onTypeChange">
            <el-tab-pane v-for="t in typeList" :key="t.typeCode" :label="t.typeName" :name="t.typeCode" />
          </el-tabs>

          <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" label-position="right">
            <el-form-item label="需求标题" prop="title">
              <el-input v-model="form.title" maxlength="100" show-word-limit placeholder="一句话概括你的需求，如：代销看板增加机构持仓维度" />
            </el-form-item>
            <el-form-item label="需求描述" prop="content">
              <el-input v-model="form.content" type="textarea" :rows="5" maxlength="2000" show-word-limit placeholder="请描述业务背景、使用场景、期望效果……" />
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="紧急程度" prop="urgency">
                  <el-select v-model="form.urgency" style="width: 100%">
                    <el-option v-for="u in urgencyOptions" :key="u.itemCode" :label="u.itemName" :value="u.itemCode" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="期望交付时间">
                  <el-date-picker v-model="form.expectDeliveryAt" type="date" value-format="YYYY-MM-DDT00:00:00" placeholder="选择日期" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 科技需求扩展字段 -->
            <template v-if="form.demandTypeCode === 'TECH'">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="关联系统">
                    <el-input v-model="ext.relatedSystem" placeholder="如：代销系统" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="关联模块">
                    <el-input v-model="ext.relatedModule" placeholder="如：数据看板" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="业务场景">
                <el-input v-model="ext.businessScenario" type="textarea" :rows="3" placeholder="什么人在什么场景下使用，解决什么问题" />
              </el-form-item>
              <el-form-item label="验收标准">
                <el-input v-model="ext.acceptanceCriteria" type="textarea" :rows="3" placeholder="怎样算完成，可量化的验收条件" />
              </el-form-item>
            </template>

            <!-- 物料需求扩展字段 -->
            <template v-else-if="form.demandTypeCode === 'MATL'">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="物料子类">
                    <el-input v-model="ext.materialSubtype" placeholder="如：宣传折页 / 易拉宝 / 海报" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="数量">
                    <el-input-number v-model="ext.quantity" :min="1" :max="999999" style="width: 100%" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="使用场景">
                    <el-input v-model="ext.usageScenario" placeholder="如：四季度路演活动" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="期望到位时间">
                    <el-date-picker v-model="ext.expectedArrivalAt" type="date" value-format="YYYY-MM-DDT00:00:00" placeholder="选择日期" style="width: 100%" />
                  </el-form-item>
                </el-col>
              </el-row>
            </template>

            <!-- 培训需求扩展字段 -->
            <template v-else-if="form.demandTypeCode === 'TRAIN'">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="培训子类">
                    <el-input v-model="ext.trainingSubtype" placeholder="如：合规培训 / 产品培训 / 技能培训" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="培训人数">
                    <el-input-number v-model="ext.traineeCount" :min="1" :max="99999" style="width: 100%" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="培训对象">
                    <el-input v-model="ext.traineeObject" placeholder="如：银行渠道新员工" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="期望完成时间">
                    <el-date-picker v-model="ext.expectedCompleteAt" type="date" value-format="YYYY-MM-DDT00:00:00" placeholder="选择日期" style="width: 100%" />
                  </el-form-item>
                </el-col>
              </el-row>
            </template>

            <!-- 自定义类型（M8 新增）无扩展字段提示 -->
            <el-alert
              v-else-if="!isBuiltinType"
              type="info"
              :closable="false"
              title="该类型无扩展字段，请在需求描述中写清业务背景与期望效果"
              style="margin-bottom: 14px"
            />

            <!-- 代办提报 -->
            <el-form-item label="代办提报">
              <el-checkbox v-model="proxyMode">为他人代提报该需求</el-checkbox>
              <div v-if="proxyMode" style="width: 100%; margin-top: 8px">
                <UserSelect v-model="form.actualDemanderId" placeholder="选择实际需求人" />
                <div class="muted">提交后提报人为你，实际需求人为所选同事；对方可在「我的提报」看到该需求</div>
              </div>
            </el-form-item>

            <!-- 附件 -->
            <el-form-item label="附件">
              <div class="upload-area">
                <el-upload
                  drag
                  multiple
                  :show-file-list="false"
                  :http-request="onUpload"
                  :disabled="uploading"
                >
                  <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                  <div class="el-upload__text">拖拽文件到此处，或 <em>点击上传</em></div>
                  <template #tip>
                    <div class="el-upload__tip">支持图片 / PDF / Office，单文件 ≤ 50MB</div>
                  </template>
                </el-upload>
                <div v-if="uploading" class="upload-progress">
                  <el-progress :percentage="uploadPercent" />
                </div>
                <div v-for="att in attachments" :key="att.id" class="att-item">
                  <el-icon><Paperclip /></el-icon>
                  <span class="att-name">{{ att.fileName }}</span>
                  <span class="muted">{{ fmtSize(att.fileSize) }}</span>
                  <el-button v-if="isImage(att)" link type="primary" @click="onPreview(att)">预览</el-button>
                  <el-button link type="danger" @click="onRemoveAttachment(att)">删除</el-button>
                </div>
              </div>
            </el-form-item>

            <el-form-item>
              <el-button :loading="savingDraft" @click="onSaveDraft">暂存草稿</el-button>
              <el-button type="primary" :loading="submitting" @click="onSubmit">提交需求</el-button>
              <el-button text @click="onReset">清空</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="7">
        <AgentGuidePanel :form-context="agentFormContext" @fill="onAgentFill" />
        <el-card shadow="never" style="margin-top: 16px">
          <template #header>填写指引</template>
          <div class="guide">
            <p><b>科技需求</b>：系统功能、数据报表、接口集成类，请写清关联系统与业务场景。</p>
            <p><b>物料需求</b>：宣传品、印刷品、礼品类，请写清数量与期望到位时间。</p>
            <p><b>培训需求</b>：课程开发、培训组织类，请写清培训对象与人数。</p>
            <el-divider />
            <p class="muted">提交后将按类型自动路由到对应承接组织，需求经理会收到受理提醒。</p>
            <p class="muted">不确定怎么写？先暂存草稿，之后可从右上角「草稿箱」继续编辑。</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 草稿箱抽屉 -->
    <el-drawer v-model="draftDrawer" title="我的草稿" size="420px">
      <el-empty v-if="!drafts.length" description="暂无草稿" />
      <div v-for="d in drafts" :key="d.id" class="draft-item" @click="onLoadDraft(d)">
        <div class="draft-title">{{ draftTitle(d) }}</div>
        <div class="muted">更新于 {{ fmtTime(d.updatedAt) }}</div>
        <el-button class="draft-del" link type="danger" @click.stop="onDeleteDraft(d)">删除</el-button>
      </div>
    </el-drawer>

    <!-- 图片预览 -->
    <el-dialog v-model="previewVisible" :title="previewName" width="640px">
      <img :src="previewUrl" style="max-width: 100%" alt="附件预览" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules, type UploadRequestOptions } from 'element-plus'
import UserSelect from '@/components/UserSelect.vue'
import AgentGuidePanel from '@/components/AgentGuidePanel.vue'
import type { GuideStructured } from '@/api/agent'
import {
  listDictItems,
  saveDraft,
  listDrafts,
  deleteDraft,
  submitDemand,
  uploadAttachment,
  deleteAttachment,
  previewAttachmentUrl,
  type AttachmentItem,
  type DraftItem,
  type DictItem
} from '@/api/demand'
import { listActiveTypes, type DemandTypeItem } from '@/api/directory'
import { useUserStore } from '@/store/modules/user'
import { fmtTime, fmtSize } from '@/utils/format'

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

const formRef = ref<FormInstance>()
const form = reactive(emptyForm())
const ext = reactive<ExtForm>({})
const proxyMode = ref(false)
const attachments = ref<AttachmentItem[]>([])
const drafts = ref<DraftItem[]>([])
const draftDrawer = ref(false)
const currentDraftId = ref<number | null>(null)
const typeList = ref<DemandTypeItem[]>([])
const urgencyOptions = ref<DictItem[]>([])
const uploading = ref(false)
const uploadPercent = ref(0)
const savingDraft = ref(false)
const submitting = ref(false)
const previewVisible = ref(false)
const previewUrl = ref('')
const previewName = ref('')

const isBuiltinType = computed(() => BUILTIN.includes(form.demandTypeCode))

/** Agent 表单上下文快照（后端合并时用户手填优先，AI 不覆盖非空字段） */
const agentFormContext = computed<Record<string, unknown>>(() => ({
  title: form.title || undefined,
  demandTypeCode: form.demandTypeCode || undefined,
  content: form.content || undefined,
  urgency: form.urgency || undefined,
  expectDeliveryAt: form.expectDeliveryAt || undefined,
  ext: Object.keys(currentExt()).length ? currentExt() : undefined
}))

/** AI 结构化回填：类型先切换（清扩展字段），再逐项应用；用户可继续编辑 */
function onAgentFill(fields: GuideStructured) {
  if (fields.demandTypeCode && typeList.value.some((t) => t.typeCode === fields.demandTypeCode)) {
    if (form.demandTypeCode !== fields.demandTypeCode) {
      form.demandTypeCode = fields.demandTypeCode
      onTypeChange()
    }
  }
  if (fields.title) {
    form.title = fields.title
  }
  if (fields.content) {
    form.content = fields.content
  }
  if (fields.urgency) {
    form.urgency = fields.urgency
  }
  if (fields.expectDeliveryAt) {
    form.expectDeliveryAt = fields.expectDeliveryAt
  }
  if (fields.ext) {
    Object.assign(ext, fields.ext)
  }
}

const rules: FormRules = {
  title: [{ required: true, message: '请输入需求标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入需求描述', trigger: 'blur' }],
  urgency: [{ required: true, message: '请选择紧急程度', trigger: 'change' }]
}

function isImage(att: AttachmentItem): boolean {
  return (att.mimeType || '').startsWith('image/')
}

function onTypeChange() {
  // 切换类型时清空扩展字段，避免串字段
  Object.keys(ext).forEach((k) => delete (ext as Record<string, unknown>)[k])
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

async function onUpload(options: UploadRequestOptions) {
  const file = options.file as File
  if (file.size > 50 * 1024 * 1024) {
    ElMessage.error('单文件不能超过 50MB')
    return
  }
  uploading.value = true
  uploadPercent.value = 0
  try {
    // 暂存附件挂在 DRAFT 业务下（bizId 用当前用户 ID 占位），提交时由后端 rebind 到需求
    const att = await uploadAttachment('DRAFT', userStore.userInfo?.id || 0, file, (p) => (uploadPercent.value = p))
    attachments.value.push(att)
    ElMessage.success(`${file.name} 上传成功`)
  } finally {
    uploading.value = false
  }
}

async function onRemoveAttachment(att: AttachmentItem) {
  await deleteAttachment(att.id)
  attachments.value = attachments.value.filter((a) => a.id !== att.id)
}

async function onPreview(att: AttachmentItem) {
  previewUrl.value = await previewAttachmentUrl(att.id)
  previewName.value = att.fileName
  previewVisible.value = true
}

function buildDraftPayload(): string {
  return JSON.stringify({
    ...form,
    ext: currentExt(),
    proxyMode: proxyMode.value,
    attachmentIds: attachments.value.map((a) => a.id)
  })
}

async function onSaveDraft() {
  if (!form.title && !form.content) {
    ElMessage.warning('草稿至少需要标题或描述')
    return
  }
  savingDraft.value = true
  try {
    const saved = await saveDraft({
      id: currentDraftId.value || undefined,
      channel: 'WEB',
      formPayload: buildDraftPayload()
    })
    currentDraftId.value = saved.id
    ElMessage.success('草稿已保存')
    loadDrafts()
  } finally {
    savingDraft.value = false
  }
}

async function loadDrafts() {
  drafts.value = await listDrafts()
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
    onTypeChange()
    Object.assign(ext, payload.ext || {})
    proxyMode.value = !!payload.proxyMode
    currentDraftId.value = d.id
    // 草稿附件不回显文件实体（已传 attachmentIds 即可），提交时后端会校验归属
    draftDrawer.value = false
    ElMessage.success('草稿已载入，可继续编辑')
  } catch {
    ElMessage.error('草稿内容解析失败')
  }
}

async function onDeleteDraft(d: DraftItem) {
  await ElMessageBox.confirm('确认删除该草稿？', '提示', { type: 'warning' })
  await deleteDraft(d.id)
  if (currentDraftId.value === d.id) {
    currentDraftId.value = null
  }
  loadDrafts()
}

async function onSubmit() {
  await formRef.value?.validate()
  if (proxyMode.value && !form.actualDemanderId) {
    ElMessage.warning('代办提报请选择实际需求人')
    return
  }
  submitting.value = true
  try {
    const demand = await submitDemand({
      draftId: currentDraftId.value || undefined,
      title: form.title,
      content: form.content,
      demandTypeCode: form.demandTypeCode,
      urgency: form.urgency,
      expectDeliveryAt: form.expectDeliveryAt,
      actualDemanderId: proxyMode.value ? form.actualDemanderId || undefined : undefined,
      channel: 'WEB',
      ext: currentExt(),
      attachmentIds: attachments.value.map((a) => a.id)
    })
    ElMessage.success(`需求 ${demand.demandNo} 提交成功`)
    router.push(`/demand/detail/${demand.id}`)
  } finally {
    submitting.value = false
  }
}

function onReset() {
  Object.assign(form, emptyForm())
  onTypeChange()
  proxyMode.value = false
  attachments.value = []
  currentDraftId.value = null
  formRef.value?.clearValidate()
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
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.type-tabs {
  margin-bottom: 8px;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.upload-area {
  width: 100%;
}

.upload-progress {
  margin-top: 8px;
}

.att-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}

.att-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guide p {
  font-size: 13px;
  line-height: 1.8;
  margin-bottom: 8px;
}

.draft-item {
  position: relative;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 10px;
  cursor: pointer;
}

.draft-item:hover {
  border-color: var(--el-color-primary);
}

.draft-title {
  font-weight: 600;
  margin-bottom: 4px;
  padding-right: 48px;
}

.draft-del {
  position: absolute;
  right: 8px;
  top: 8px;
}
</style>
