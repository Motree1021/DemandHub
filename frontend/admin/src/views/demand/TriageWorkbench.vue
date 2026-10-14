<template>
  <el-card>
    <el-tabs v-model="tab">
      <el-tab-pane name="queue">
        <template #label>
          受理队列
          <el-badge v-if="counts.queue" :value="counts.queue" type="warning" class="tab-badge" />
        </template>
        <div class="toolbar">
          <el-select v-model="queueQuery.urgency" placeholder="紧急度" clearable class="sel" @change="loadQueue(1)">
            <el-option label="特急" value="CRITICAL" />
            <el-option label="紧急" value="URGENT" />
            <el-option label="普通" value="NORMAL" />
          </el-select>
          <el-select v-model="queueQuery.typeCode" placeholder="需求类型" clearable class="sel" @change="loadQueue(1)">
            <el-option v-for="(label, code) in TYPE_META" :key="code" :label="label" :value="code" />
          </el-select>
          <el-button type="primary" @click="loadQueue(1)">查询</el-button>
        </div>
        <el-table :data="queueRows" v-loading="loading" stripe @row-click="goDetail">
          <el-table-column prop="demandNo" label="编号" width="170" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
          </el-table-column>
          <el-table-column label="紧急度" width="90">
            <template #default="{ row }"><UrgencyTag :urgency="row.urgency" /></template>
          </el-table-column>
          <el-table-column prop="submitterName" label="提报人" width="100" />
          <el-table-column prop="submittedAt" label="提交时间" width="165" />
          <el-table-column label="操作" width="170" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click.stop="accept(row)">受理</el-button>
              <el-button size="small" type="warning" link @click.stop="openReturn(row)">打回</el-button>
              <el-button size="small" type="danger" link @click.stop="openClose(row)">关闭</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination class="pager" layout="total, prev, pager, next" :total="queueTotal"
                       :page-size="queueQuery.size" :current-page="queueQuery.page" @current-change="loadQueue" />
      </el-tab-pane>

      <el-tab-pane name="pool">
        <template #label>
          处理池
          <el-badge v-if="counts.pool" :value="counts.pool" type="primary" class="tab-badge" />
        </template>
        <div class="toolbar">
          <el-select v-model="poolQuery.urgency" placeholder="紧急度" clearable class="sel" @change="loadPool(1)">
            <el-option label="特急" value="CRITICAL" />
            <el-option label="紧急" value="URGENT" />
            <el-option label="普通" value="NORMAL" />
          </el-select>
          <el-button type="primary" @click="loadPool(1)">查询</el-button>
        </div>
        <el-table :data="poolRows" v-loading="loading" stripe @row-click="goDetail">
          <el-table-column prop="demandNo" label="编号" width="170" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <el-table-column label="类型" width="110">
            <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
          </el-table-column>
          <el-table-column label="紧急度" width="90">
            <template #default="{ row }"><UrgencyTag :urgency="row.urgency" /></template>
          </el-table-column>
          <el-table-column prop="submitterName" label="提报人" width="100" />
          <el-table-column prop="submittedAt" label="提交时间" width="165" />
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click.stop="openAssign(row)">分派</el-button>
              <el-button size="small" type="primary" link @click.stop="openChangeType(row)">改型</el-button>
              <el-button size="small" type="danger" link @click.stop="openClose(row)">关闭</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination class="pager" layout="total, prev, pager, next" :total="poolTotal"
                       :page-size="poolQuery.size" :current-page="poolQuery.page" @current-change="loadPool" />
      </el-tab-pane>
    </el-tabs>

    <!-- 打回：原因必填，提报人按此补充 -->
    <el-dialog v-model="returnVisible" :title="`打回：${target?.demandNo}`" width="480px">
      <el-form ref="returnRef" :model="returnForm" :rules="reasonRules" label-width="90px">
        <el-form-item label="打回原因" prop="reason">
          <el-input v-model="returnForm.reason" type="textarea" :rows="3" maxlength="512"
                    placeholder="将展示给提报人，说明需要补充的内容" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="returnVisible = false">取消</el-button>
        <el-button type="warning" :loading="submitting" @click="submitReturn">确认打回</el-button>
      </template>
    </el-dialog>

    <!-- 关闭：原因必填；重复需求可关联主需求留痕 -->
    <el-dialog v-model="closeVisible" :title="`关闭：${target?.demandNo}`" width="480px">
      <el-form ref="closeRef" :model="closeForm" :rules="reasonRules" label-width="90px">
        <el-form-item label="关闭原因" prop="reason">
          <el-input v-model="closeForm.reason" type="textarea" :rows="3" maxlength="256" />
        </el-form-item>
        <el-form-item label="重复于">
          <el-input v-model="closeForm.duplicateOfId" placeholder="选填：主需求 ID（重复关闭时填写）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closeVisible = false">取消</el-button>
        <el-button type="danger" :loading="submitting" @click="submitClose">确认关闭</el-button>
      </template>
    </el-dialog>

    <!-- 分派：选择处理人 -->
    <el-dialog v-model="assignVisible" :title="`分派：${target?.demandNo}`" width="480px">
      <el-form ref="assignRef" :model="assignForm" :rules="assignRules" label-width="90px">
        <el-form-item label="处理人" prop="assigneeId">
          <el-select v-model="assignForm.assigneeId" placeholder="选择处理人" class="full">
            <el-option v-for="a in assignees" :key="a.id" :value="a.id"
                       :label="`${a.name}${a.department ? '（' + a.department + '）' : ''}`" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="assignForm.comment" type="textarea" :rows="2" maxlength="512" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitAssign">确认分派</el-button>
      </template>
    </el-dialog>

    <!-- 改型：主状态不变，子类型清空重收集 -->
    <el-dialog v-model="typeVisible" :title="`类型修正：${target?.demandNo}`" width="480px">
      <el-form ref="typeRef" :model="typeForm" :rules="typeRules" label-width="90px">
        <el-form-item label="新类型" prop="newTypeCode">
          <el-select v-model="typeForm.newTypeCode" placeholder="选择新类型" class="full">
            <el-option v-for="(label, code) in TYPE_META" :key="code" :label="label" :value="code" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="typeForm.comment" type="textarea" :rows="2" maxlength="512" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="typeVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitChangeType">确认修正</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { triageApi } from '@/api'
import type { AssigneeOption, DemandRow } from '@/api'
import { ApiError } from '@/api/request'
import { TYPE_META, typeLabel } from '@/utils/status'
import UrgencyTag from '@/components/UrgencyTag.vue'

const router = useRouter()
const tab = ref<'queue' | 'pool'>('queue')
const loading = ref(false)
const submitting = ref(false)
const counts = reactive({ queue: 0, pool: 0 })

const queueRows = ref<DemandRow[]>([])
const queueTotal = ref(0)
const queueQuery = reactive({ page: 1, size: 20, urgency: '', typeCode: '' })
const poolRows = ref<DemandRow[]>([])
const poolTotal = ref(0)
const poolQuery = reactive({ page: 1, size: 20, urgency: '' })

const target = ref<DemandRow | null>(null)
const assignees = ref<AssigneeOption[]>([])

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function loadCounts() {
  try {
    Object.assign(counts, await triageApi.counts())
  } catch { /* 计数失败不阻塞列表 */ }
}

async function loadQueue(page = queueQuery.page) {
  queueQuery.page = page
  loading.value = true
  try {
    const data = await triageApi.queue({
      page: queueQuery.page, size: queueQuery.size,
      urgency: queueQuery.urgency || undefined, typeCode: queueQuery.typeCode || undefined,
    })
    queueRows.value = data.records
    queueTotal.value = data.total
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

async function loadPool(page = poolQuery.page) {
  poolQuery.page = page
  loading.value = true
  try {
    const data = await triageApi.pool({
      page: poolQuery.page, size: poolQuery.size, urgency: poolQuery.urgency || undefined,
    })
    poolRows.value = data.records
    poolTotal.value = data.total
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

async function reload() {
  await Promise.all([loadCounts(), tab.value === 'queue' ? loadQueue() : loadPool()])
}

function goDetail(row: DemandRow) {
  router.push(`/demands/${row.id}`)
}

async function accept(row: DemandRow) {
  try {
    await ElMessageBox.confirm(`受理需求「${row.title}」？受理后进入处理池等待分派。`, '受理确认',
      { type: 'warning', confirmButtonText: '受理', cancelButtonText: '取消' })
  } catch { return }
  try {
    await triageApi.accept(row.id)
    ElMessage.success('已受理')
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '受理失败'))
  }
}

const reasonRules: FormRules = {
  reason: [{ required: true, message: '原因必填', trigger: 'blur' }],
}

const returnVisible = ref(false)
const returnRef = ref<FormInstance>()
const returnForm = reactive({ reason: '' })
function openReturn(row: DemandRow) {
  target.value = row
  returnForm.reason = ''
  returnVisible.value = true
}
async function submitReturn() {
  await returnRef.value?.validate().catch(() => Promise.reject())
  if (!target.value) return
  submitting.value = true
  try {
    await triageApi.returnDemand(target.value.id, returnForm.reason)
    ElMessage.success('已打回提报人补充')
    returnVisible.value = false
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '打回失败'))
  } finally {
    submitting.value = false
  }
}

const closeVisible = ref(false)
const closeRef = ref<FormInstance>()
const closeForm = reactive({ reason: '', duplicateOfId: '' })
function openClose(row: DemandRow) {
  target.value = row
  Object.assign(closeForm, { reason: '', duplicateOfId: '' })
  closeVisible.value = true
}
async function submitClose() {
  await closeRef.value?.validate().catch(() => Promise.reject())
  if (!target.value) return
  submitting.value = true
  try {
    const dupId = closeForm.duplicateOfId.trim() ? Number(closeForm.duplicateOfId.trim()) : undefined
    if (dupId !== undefined && (!Number.isInteger(dupId) || dupId <= 0)) {
      ElMessage.warning('「重复于」请填写主需求 ID（正整数）')
      return
    }
    await triageApi.close(target.value.id, closeForm.reason, dupId)
    ElMessage.success('已关闭')
    closeVisible.value = false
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '关闭失败'))
  } finally {
    submitting.value = false
  }
}

const assignVisible = ref(false)
const assignRef = ref<FormInstance>()
const assignForm = reactive({ assigneeId: undefined as number | undefined, comment: '' })
const assignRules: FormRules = {
  assigneeId: [{ required: true, message: '请选择处理人', trigger: 'change' }],
}
async function openAssign(row: DemandRow) {
  target.value = row
  Object.assign(assignForm, { assigneeId: undefined, comment: '' })
  if (!assignees.value.length) {
    try {
      assignees.value = await triageApi.assignees()
    } catch (e) {
      ElMessage.error(errorMessage(e, '处理人列表加载失败'))
      return
    }
  }
  assignVisible.value = true
}
async function submitAssign() {
  await assignRef.value?.validate().catch(() => Promise.reject())
  if (!target.value || assignForm.assigneeId === undefined) return
  submitting.value = true
  try {
    await triageApi.assign(target.value.id, assignForm.assigneeId, assignForm.comment || undefined)
    ElMessage.success('已分派')
    assignVisible.value = false
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '分派失败'))
  } finally {
    submitting.value = false
  }
}

const typeVisible = ref(false)
const typeRef = ref<FormInstance>()
const typeForm = reactive({ newTypeCode: '', comment: '' })
const typeRules: FormRules = {
  newTypeCode: [{ required: true, message: '请选择新类型', trigger: 'change' }],
}
function openChangeType(row: DemandRow) {
  target.value = row
  Object.assign(typeForm, { newTypeCode: '', comment: '' })
  typeVisible.value = true
}
async function submitChangeType() {
  await typeRef.value?.validate().catch(() => Promise.reject())
  if (!target.value) return
  submitting.value = true
  try {
    await triageApi.changeType(target.value.id, typeForm.newTypeCode, typeForm.comment || undefined)
    ElMessage.success('已修正类型')
    typeVisible.value = false
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '修正失败'))
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadCounts()
  loadQueue(1)
  loadPool(1)
})
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.sel { width: 140px; }
.full { width: 100%; }
.pager { margin-top: 16px; justify-content: flex-end; }
.tab-badge { margin-left: 6px; vertical-align: super; }
:deep(.el-table__row) { cursor: pointer; }
</style>
