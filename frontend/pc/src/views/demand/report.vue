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
            <el-form-item label="需求标题" prop="title" :class="{ 'ai-flash': aiFlash.has('title') }">
              <el-input v-model="form.title" maxlength="100" show-word-limit placeholder="一句话概括你的需求，如：代销看板增加机构持仓维度" />
            </el-form-item>
            <el-form-item label="需求描述" prop="content" :class="{ 'ai-flash': aiFlash.has('content') }">
              <div class="content-editor">
                <div class="content-toolbar">
                  <el-button link type="primary" size="small" @click="insertContentTemplate">插入模板</el-button>
                </div>
                <el-input v-model="form.content" type="textarea" :rows="5" maxlength="2000" show-word-limit placeholder="请描述现状痛点与期望效果……可点右上方「插入模板」按两段式填写；使用场景（谁·什么时候·做什么）请在下方「业务场景」一句话写清" />
              </div>
            </el-form-item>
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="紧急程度" prop="urgency" :class="{ 'ai-flash': aiFlash.has('urgency') }">
                  <el-select v-model="form.urgency" style="width: 100%">
                    <el-option v-for="u in urgencyOptions" :key="u.itemCode" :label="u.itemName" :value="u.itemCode" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="期望交付时间" :class="{ 'ai-flash': aiFlash.has('expectDeliveryAt') }">
                  <el-date-picker v-model="form.expectDeliveryAt" type="date" value-format="YYYY-MM-DDT00:00:00" placeholder="选择日期" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 科技需求扩展字段 -->
            <template v-if="form.demandTypeCode === 'TECH'">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="需求子类" :class="{ 'ai-flash': aiFlash.has('techSubtype') }">
                    <el-select v-model="ext.techSubtype" clearable placeholder="选择后会出现针对性补充项（选填）" style="width: 100%">
                      <el-option v-for="s in techSubtypeOptions" :key="s.itemCode" :label="s.itemName" :value="s.itemCode" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="关联系统" :class="{ 'ai-flash': aiFlash.has('relatedSystem') }">
                    <el-select
                      v-model="ext.relatedSystem"
                      filterable
                      allow-create
                      default-first-option
                      :reserve-keyword="false"
                      clearable
                      placeholder="选择或输入系统名称"
                      style="width: 100%"
                    >
                      <el-option v-for="s in relatedSystemOptions" :key="s.itemCode" :label="s.itemName" :value="s.itemName" />
                    </el-select>
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="关联模块" :class="{ 'ai-flash': aiFlash.has('relatedModule') }">
                    <el-input v-model="ext.relatedModule" placeholder="如：数据看板" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-form-item label="业务场景" :class="{ 'ai-flash': aiFlash.has('businessScenario') }">
                <el-input v-model="ext.businessScenario" type="textarea" :rows="3" placeholder="作为__（角色），在__（时间/频率），需要__（做什么）。示例：机构业务部客户经理，每天晨会前查各机构持仓" />
              </el-form-item>
              <el-form-item label="验收标准" :class="{ 'ai-flash': aiFlash.has('acceptanceCriteria') }">
                <el-input v-model="ext.acceptanceCriteria" type="textarea" :rows="3" placeholder="当__时，系统应__；检查项：①__②__。示例：连续一周与核心系统对账误差为0" />
              </el-form-item>

              <!-- 选填补充区：价值与影响 + 子类差异要素（P10 需求启发：渐进披露降低填写负担） -->
              <el-collapse v-model="extCollapse" class="ext-collapse">
                <el-collapse-item title="补充信息（选填 · 写得越具体受理越快）" name="more">
                  <el-form-item label="价值与影响" :class="{ 'ai-flash': aiFlash.has('valueImpact') }">
                    <el-input v-model="ext.valueImpact" type="textarea" :rows="2" placeholder="影响多少人/部门？每次能省多少时间？不做会怎样？示例：20多名客户经理每人每天节省约40分钟手工整理" />
                  </el-form-item>

                  <!-- 系统开发 -->
                  <template v-if="ext.techSubtype === 'SYS_DEV'">
                    <el-form-item label="涉及功能/流程" :class="{ 'ai-flash': aiFlash.has('devFeatures') }">
                      <el-input v-model="ext.devFeatures" placeholder="如：代销看板-机构持仓页签，涉及查询与导出流程" />
                    </el-form-item>
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <el-form-item label="角色与权限" :class="{ 'ai-flash': aiFlash.has('devPermission') }">
                          <el-input v-model="ext.devPermission" placeholder="如：机构业务部全员可查，仅主管可导出" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="性能/安全" :class="{ 'ai-flash': aiFlash.has('devQuality') }">
                          <el-input v-model="ext.devQuality" placeholder="如：查询3秒内返回；客户敏感信息需脱敏" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                  </template>

                  <!-- 数据报表 -->
                  <template v-else-if="ext.techSubtype === 'DATA_RPT'">
                    <el-form-item label="维度与口径" :class="{ 'ai-flash': aiFlash.has('dataDimensions') }">
                      <el-input v-model="ext.dataDimensions" placeholder="如：按机构汇总前一交易日持仓（市值/份额），与核心系统口径一致" />
                    </el-form-item>
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <el-form-item label="数据来源" :class="{ 'ai-flash': aiFlash.has('dataSource') }">
                          <el-input v-model="ext.dataSource" placeholder="如：代销系统交易库 + 核心系统持仓" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="刷新频率" :class="{ 'ai-flash': aiFlash.has('refreshFrequency') }">
                          <el-input v-model="ext.refreshFrequency" placeholder="如：每个交易日早8:00前刷新" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                    <el-form-item label="导出要求" :class="{ 'ai-flash': aiFlash.has('exportRequirement') }">
                      <el-input v-model="ext.exportRequirement" placeholder="如：支持导出Excel，字段与页面一致" />
                    </el-form-item>
                  </template>

                  <!-- 系统集成 -->
                  <template v-else-if="ext.techSubtype === 'SYS_INT'">
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <el-form-item label="对接系统" :class="{ 'ai-flash': aiFlash.has('intTargetSystem') }">
                          <el-input v-model="ext.intTargetSystem" placeholder="如：与CRM双向对接" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="流向与触发" :class="{ 'ai-flash': aiFlash.has('intDataFlow') }">
                          <el-input v-model="ext.intDataFlow" placeholder="如：客户风险等级由CRM实时推送" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <el-form-item label="时效要求" :class="{ 'ai-flash': aiFlash.has('intTimeliness') }">
                          <el-input v-model="ext.intTimeliness" placeholder="如：数据延迟不超过5分钟" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="异常处理" :class="{ 'ai-flash': aiFlash.has('intException') }">
                          <el-input v-model="ext.intException" placeholder="如：同步失败自动重试并通知运维" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                  </template>

                  <!-- 运维优化 -->
                  <template v-else-if="ext.techSubtype === 'OPS_OPT'">
                    <el-form-item label="问题现象" :class="{ 'ai-flash': aiFlash.has('opsProblem') }">
                      <el-input v-model="ext.opsProblem" placeholder="如：月末批量导出Excel等待约10分钟，经常超时" />
                    </el-form-item>
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <el-form-item label="影响范围" :class="{ 'ai-flash': aiFlash.has('opsScope') }">
                          <el-input v-model="ext.opsScope" placeholder="如：全渠道客户经理，每月初集中使用" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="期望目标" :class="{ 'ai-flash': aiFlash.has('opsTarget') }">
                          <el-input v-model="ext.opsTarget" placeholder="如：导出1分钟内完成" />
                        </el-form-item>
                      </el-col>
                    </el-row>
                  </template>
                </el-collapse-item>
              </el-collapse>
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
            <p><b>科技需求</b>：系统功能、数据报表、接口集成类。先选「需求子类」，表单会出现针对性补充项。</p>
            <template v-if="form.demandTypeCode === 'TECH'">
              <p v-if="subtypeGuide" class="subtype-guide">{{ subtypeGuide }}</p>
              <p class="muted">业务场景写清"谁·什么时候·做什么"；验收标准要可检查（时间/误差/检查项），避免"好用、尽快"这类词。</p>
            </template>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
  techSubtype?: string
  relatedSystem?: string
  relatedModule?: string
  businessScenario?: string
  acceptanceCriteria?: string
  valueImpact?: string
  devFeatures?: string
  devPermission?: string
  devQuality?: string
  dataDimensions?: string
  dataSource?: string
  refreshFrequency?: string
  exportRequirement?: string
  intTargetSystem?: string
  intDataFlow?: string
  intTimeliness?: string
  intException?: string
  opsProblem?: string
  opsScope?: string
  opsTarget?: string
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
const techSubtypeOptions = ref<DictItem[]>([])
const relatedSystemOptions = ref<DictItem[]>([])
const extCollapse = ref<string[]>([])
/** AI 回填字段高亮（1.8s 后消失）：key 为表单字段键/ext 键 */
const aiFlash = ref<Set<string>>(new Set())
let flashTimer: number | undefined
const uploading = ref(false)
const uploadPercent = ref(0)
const savingDraft = ref(false)
const submitting = ref(false)
const previewVisible = ref(false)
const previewUrl = ref('')
const previewName = ref('')

const isBuiltinType = computed(() => BUILTIN.includes(form.demandTypeCode))

/** 子类差异化填写指引（需求启发：不同问题问不同内容） */
const subtypeGuide = computed(() => {
  switch (ext.techSubtype) {
    case 'SYS_DEV':
      return '系统开发类：重点写清涉及的功能/流程、谁能用（角色权限）、有没有性能或安全要求。'
    case 'DATA_RPT':
      return '数据报表类：口径不清是返工首因——请写清维度与指标口径、数据来源、刷新频率、要不要导出。'
    case 'SYS_INT':
      return '系统集成类：写清和哪个系统对接、数据往哪流、多久算及时、出错了怎么办。'
    case 'OPS_OPT':
      return '运维优化类：写清现在的现象（多慢/什么错）、影响多少人、期望达到什么目标。'
    default:
      return ''
  }
})

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
  const filled: string[] = []
  if (fields.title) {
    form.title = fields.title
    filled.push('title')
  }
  if (fields.content) {
    form.content = fields.content
    filled.push('content')
  }
  if (fields.urgency) {
    form.urgency = fields.urgency
    filled.push('urgency')
  }
  if (fields.expectDeliveryAt) {
    form.expectDeliveryAt = fields.expectDeliveryAt
    filled.push('expectDeliveryAt')
  }
  if (fields.ext) {
    Object.assign(ext, fields.ext)
    filled.push(...Object.keys(fields.ext))
    // AI 回填了子类/补充要素时展开折叠区，让用户看见
    if (fields.ext.techSubtype || filled.some((k) => k === 'valueImpact')) {
      extCollapse.value = ['more']
    }
  }
  flashFields(filled)
}

/** AI 回填字段高亮反馈：1.8s 闪烁后自动消失 */
function flashFields(keys: string[]) {
  if (!keys.length) {
    return
  }
  aiFlash.value = new Set(keys)
  window.clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => {
    aiFlash.value = new Set()
  }, 1800)
}

/** 需求描述两段式模板（现状痛点/期望效果），仅在空白时插入避免覆盖用户内容 */
function insertContentTemplate() {
  if (form.content.trim()) {
    ElMessage.info('已有内容，可直接在原文上按「现状痛点/期望效果」补充')
    return
  }
  form.content = '【现状痛点】\n\n\n【期望效果】\n'
}

/** 子类差异要素 → 提交时拼装进需求描述的固定段落（混合存储：关键字段加列，其余模板化） */
const EXTRA_SECTIONS: Record<string, [string, keyof ExtForm][]> = {
  SYS_DEV: [
    ['涉及功能/流程', 'devFeatures'],
    ['使用角色与权限', 'devPermission'],
    ['性能/安全要求', 'devQuality']
  ],
  DATA_RPT: [
    ['数据维度与口径', 'dataDimensions'],
    ['数据来源系统', 'dataSource'],
    ['使用/刷新频率', 'refreshFrequency'],
    ['导出要求', 'exportRequirement']
  ],
  SYS_INT: [
    ['对接系统', 'intTargetSystem'],
    ['数据流向与触发', 'intDataFlow'],
    ['时效要求', 'intTimeliness'],
    ['异常处理期望', 'intException']
  ],
  OPS_OPT: [
    ['问题现象', 'opsProblem'],
    ['影响范围', 'opsScope'],
    ['期望目标', 'opsTarget']
  ]
}

function buildContent(): string {
  let content = form.content.trim()
  const sections: [string, unknown][] = [['价值与影响', ext.valueImpact]]
  for (const [label, key] of EXTRA_SECTIONS[ext.techSubtype || ''] || []) {
    sections.push([label, ext[key]])
  }
  for (const [label, v] of sections) {
    if (v !== undefined && v !== null && String(v).trim()) {
      content += `\n\n【${label}】\n${String(v).trim()}`
    }
  }
  return content
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
  extCollapse.value = []
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
      content: form.demandTypeCode === 'TECH' ? buildContent() : form.content,
      demandTypeCode: form.demandTypeCode,
      urgency: form.urgency,
      expectDeliveryAt: form.expectDeliveryAt,
      actualDemanderId: proxyMode.value ? form.actualDemanderId || undefined : undefined,
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
  techSubtypeOptions.value = await listDictItems('TECH_SUBTYPE')
  relatedSystemOptions.value = await listDictItems('RELATED_SYSTEM')
  loadDrafts()
})

// 选中子类后展开补充区，露出针对性差异要素
watch(
  () => ext.techSubtype,
  (v) => {
    if (v && form.demandTypeCode === 'TECH' && !extCollapse.value.length) {
      extCollapse.value = ['more']
    }
  }
)
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

/* 需求描述编辑器：插入模板按钮置于输入框右上方，避免挤占表单标签换行 */
.content-editor {
  width: 100%;
}

.content-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 2px;
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

.subtype-guide {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  border-radius: 6px;
  padding: 6px 8px;
}

.ext-collapse {
  margin-bottom: 18px;
  border-top: none;
}

.ext-collapse :deep(.el-collapse-item__header) {
  color: var(--el-color-primary);
  font-weight: 600;
}

/* AI 回填字段高亮闪烁（1.8s） */
.ai-flash {
  animation: ai-flash-bg 0.6s ease-in-out 3;
  border-radius: 6px;
}

@keyframes ai-flash-bg {
  50% {
    background: var(--el-color-success-light-8);
  }
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
