<template>
  <div class="mgr-page">
    <el-row :gutter="16">
      <el-col :span="24">
        <!-- 待受理队列 -->
        <el-card shadow="never" class="mb16">
          <template #header>
            <div class="card-header">
              <span>待受理队列</span>
              <el-badge :value="queueCount" :max="99" type="danger" />
            </div>
          </template>
          <div class="filter-bar">
            <el-select v-model="queueQuery.urgency" placeholder="全部紧急程度" clearable style="width: 130px" @change="loadQueue(1)">
              <el-option label="普通" value="NORMAL" />
              <el-option label="紧急" value="URGENT" />
              <el-option label="特急" value="CRITICAL" />
            </el-select>
            <el-select v-model="queueQuery.demandTypeCode" placeholder="全部类型" clearable style="width: 130px" @change="loadQueue(1)">
              <el-option v-for="t in typeList" :key="t.typeCode" :label="t.typeName" :value="t.typeCode" />
            </el-select>
          </div>
          <el-table :data="queue" v-loading="queueLoading" border>
            <el-table-column label="编号" width="165">
              <template #default="{ row }">
                <el-link type="primary" @click="goDetail(row.id)">{{ row.demandNo }}</el-link>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
            </el-table-column>
            <el-table-column label="紧急" width="80">
              <template #default="{ row }">
                <el-tag :type="urgencyTagType(row.urgency)" size="small">{{ urgencyLabel(row.urgency) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="150">
              <template #default="{ row }">{{ fmtTime(row.submittedAt) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" @click="openAccept(row)">受理</el-button>
                <el-button size="small" type="warning" plain @click="openReturn(row)">退回</el-button>
                <el-button size="small" type="danger" plain @click="openClose(row)">关闭</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination
            class="pager"
            layout="total, prev, pager, next"
            :total="queueTotal"
            :page-size="queueQuery.size"
            :current-page="queueQuery.current"
            @current-change="loadQueue"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 待分派需求池 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>待分派需求池（TRIAGE）</span>
          <el-select v-model="poolQuery.urgency" placeholder="全部紧急程度" clearable style="width: 130px" @change="loadPool(1)">
            <el-option label="普通" value="NORMAL" />
            <el-option label="紧急" value="URGENT" />
            <el-option label="特急" value="CRITICAL" />
          </el-select>
        </div>
      </template>
      <el-table :data="pool" v-loading="poolLoading" border>
        <el-table-column label="编号" width="165">
          <template #default="{ row }">
            <el-link type="primary" @click="goDetail(row.id)">{{ row.demandNo }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
        </el-table-column>
        <el-table-column label="紧急" width="80">
          <template #default="{ row }">
            <el-tag :type="urgencyTagType(row.urgency)" size="small">{{ urgencyLabel(row.urgency) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.submittedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="openAssign(row)">分派</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="poolTotal"
        :page-size="poolQuery.size"
        :current-page="poolQuery.current"
        @current-change="loadPool"
      />
    </el-card>

    <!-- 受理弹窗 -->
    <el-dialog v-model="dlg.accept" :title="`受理 ${current?.demandNo || ''}`" width="440px">
      <el-input v-model="opComment" type="textarea" :rows="3" placeholder="受理意见（选填）" />
      <template #footer>
        <el-button @click="dlg.accept = false">取消</el-button>
        <el-button type="primary" :loading="opLoading" @click="onAccept">确认受理</el-button>
      </template>
    </el-dialog>

    <!-- 退回弹窗 -->
    <el-dialog v-model="dlg.returnBack" :title="`退回 ${current?.demandNo || ''}`" width="440px">
      <el-input v-model="opComment" type="textarea" :rows="3" placeholder="请说明需要补充的内容（必填）" />
      <template #footer>
        <el-button @click="dlg.returnBack = false">取消</el-button>
        <el-button type="warning" :disabled="!opComment.trim()" :loading="opLoading" @click="onReturn">确认退回</el-button>
      </template>
    </el-dialog>

    <!-- 关闭弹窗 -->
    <el-dialog v-model="dlg.close" :title="`关闭 ${current?.demandNo || ''}`" width="440px">
      <el-input v-model="opComment" type="textarea" :rows="3" placeholder="请填写关闭原因（必填）" />
      <template #footer>
        <el-button @click="dlg.close = false">取消</el-button>
        <el-button type="danger" :disabled="!opComment.trim()" :loading="opLoading" @click="onClose">确认关闭</el-button>
      </template>
    </el-dialog>

    <!-- 分派弹窗 -->
    <el-dialog v-model="dlg.assign" :title="`分派 ${current?.demandNo || ''}`" width="440px">
      <el-form label-width="80px">
        <el-form-item label="处理人" required>
          <UserSelect v-model="assigneeId" placeholder="选择处理人" />
        </el-form-item>
        <el-form-item label="分派意见">
          <el-input v-model="opComment" type="textarea" :rows="3" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg.assign = false">取消</el-button>
        <el-button type="primary" :disabled="!assigneeId" :loading="opLoading" @click="onAssign">确认分派</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import UserSelect from '@/components/UserSelect.vue'
import {
  triageQueue,
  triageQueueCount,
  triagePool,
  acceptDemand,
  returnDemand,
  closeDemand,
  assignDemand,
  type DemandEntity
} from '@/api/demand'
import { listActiveTypes, type DemandTypeItem } from '@/api/directory'
import { urgencyLabel, urgencyTagType, typeLabel, fmtTime } from '@/utils/format'

const router = useRouter()

const queue = ref<DemandEntity[]>([])
const queueTotal = ref(0)
const queueCount = ref(0)
const queueLoading = ref(false)
const pool = ref<DemandEntity[]>([])
const poolTotal = ref(0)
const poolLoading = ref(false)
const typeList = ref<DemandTypeItem[]>([])

const queueQuery = reactive({ current: 1, size: 10, urgency: undefined as string | undefined, demandTypeCode: undefined as string | undefined })
const poolQuery = reactive({ current: 1, size: 10, urgency: undefined as string | undefined })

const dlg = reactive({ accept: false, returnBack: false, close: false, assign: false })
const current = ref<DemandEntity | null>(null)
const opComment = ref('')
const assigneeId = ref<number | null>(null)
const opLoading = ref(false)

async function loadQueue(page = queueQuery.current) {
  queueQuery.current = page
  queueLoading.value = true
  try {
    const data = await triageQueue({ ...queueQuery })
    queue.value = data.records
    queueTotal.value = data.total
    queueCount.value = await triageQueueCount({ urgency: queueQuery.urgency, demandTypeCode: queueQuery.demandTypeCode })
  } finally {
    queueLoading.value = false
  }
}

async function loadPool(page = poolQuery.current) {
  poolQuery.current = page
  poolLoading.value = true
  try {
    const data = await triagePool({ ...poolQuery })
    pool.value = data.records
    poolTotal.value = data.total
  } finally {
    poolLoading.value = false
  }
}

function refresh() {
  loadQueue()
  loadPool()
}

function goDetail(id: number) {
  router.push(`/demand/detail/${id}`)
}

function openAccept(row: DemandEntity) {
  current.value = row
  opComment.value = ''
  dlg.accept = true
}

function openReturn(row: DemandEntity) {
  current.value = row
  opComment.value = ''
  dlg.returnBack = true
}

function openClose(row: DemandEntity) {
  current.value = row
  opComment.value = ''
  dlg.close = true
}

function openAssign(row: DemandEntity) {
  current.value = row
  opComment.value = ''
  assigneeId.value = null
  dlg.assign = true
}

async function runOp(fn: () => Promise<unknown>, msg: string, dlgKey: keyof typeof dlg) {
  opLoading.value = true
  try {
    await fn()
    ElMessage.success(msg)
    dlg[dlgKey] = false
    refresh()
  } finally {
    opLoading.value = false
  }
}

function onAccept() {
  runOp(() => acceptDemand(current.value!.id, opComment.value || undefined), '已受理', 'accept')
}

function onReturn() {
  runOp(() => returnDemand(current.value!.id, opComment.value), '已退回', 'returnBack')
}

function onClose() {
  runOp(() => closeDemand(current.value!.id, opComment.value), '已关闭', 'close')
}

function onAssign() {
  runOp(() => assignDemand(current.value!.id, assigneeId.value!, opComment.value || undefined), '分派成功', 'assign')
}

onMounted(async () => {
  typeList.value = await listActiveTypes()
  refresh()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}

.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
