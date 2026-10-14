<template>
  <div class="page">
    <el-card class="card">
      <template #header>
        <div class="card-header">
          <span>处理池 · 可领取</span>
          <el-button size="small" @click="loadPool(1)">刷新</el-button>
        </div>
      </template>
      <el-table :data="poolRows" v-loading="poolLoading" stripe @row-click="goDetail">
        <el-table-column prop="demandNo" label="编号" width="170" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
        </el-table-column>
        <el-table-column label="紧急度" width="90">
          <template #default="{ row }"><UrgencyTag :urgency="row.urgency" /></template>
        </el-table-column>
        <el-table-column prop="submittedAt" label="提交时间" width="165" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click.stop="claim(row)">领取</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination class="pager" layout="total, prev, pager, next" :total="poolTotal"
                     :page-size="poolQuery.size" :current-page="poolQuery.page" @current-change="loadPool" />
    </el-card>

    <el-card class="card">
      <template #header>
        <div class="card-header">
          <span>我的处理单</span>
          <el-radio-group v-model="mineQuery.status" size="small" @change="loadMine(1)">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="ANALYZING">分析中</el-radio-button>
            <el-radio-button value="SOLUTION_REVIEW">待评审</el-radio-button>
            <el-radio-button value="CONFIRMED">已确认</el-radio-button>
            <el-radio-button value="IN_PROGRESS">处理中</el-radio-button>
            <el-radio-button value="ACCEPTANCE">待验收</el-radio-button>
            <el-radio-button value="DONE">已完成</el-radio-button>
          </el-radio-group>
        </div>
      </template>
      <el-table :data="mineRows" v-loading="mineLoading" stripe @row-click="goDetail">
        <el-table-column prop="demandNo" label="编号" width="170" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            <StatusTag :status="row.status" :on-hold="row.onHold" :hold-reason="row.holdReason" />
          </template>
        </el-table-column>
        <el-table-column label="紧急度" width="90">
          <template #default="{ row }"><UrgencyTag :urgency="row.urgency" /></template>
        </el-table-column>
        <el-table-column prop="submitterName" label="提报人" width="100" />
        <el-table-column prop="expectDeliveryAt" label="期望交付" width="110">
          <template #default="{ row }">{{ row.expectDeliveryAt || '—' }}</template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="165" />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.onHold" size="small" type="success" link @click.stop="resume(row)">恢复</el-button>
            <template v-else>
              <el-button v-if="row.status === 'CONFIRMED'" size="small" type="primary" link
                         @click.stop="start(row)">开始处理</el-button>
              <el-button v-if="row.status === 'ANALYZING'" size="small" type="primary" link
                         @click.stop="goSolution(row)">写方案</el-button>
              <el-button v-if="row.status === 'IN_PROGRESS'" size="small" type="success" link
                         @click.stop="submitAcceptance(row)">提交验收</el-button>
              <el-button v-if="['ANALYZING', 'SOLUTION_REVIEW', 'CONFIRMED', 'IN_PROGRESS'].includes(row.status)"
                         size="small" type="warning" link @click.stop="hold(row)">挂起</el-button>
              <el-button v-if="row.status === 'ANALYZING'" size="small" type="danger" link
                         @click.stop="returnPool(row)">退单</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination class="pager" layout="total, prev, pager, next" :total="mineTotal"
                     :page-size="mineQuery.size" :current-page="mineQuery.page" @current-change="loadMine" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { flowApi, triageApi } from '@/api'
import type { DemandRow } from '@/api'
import { ApiError } from '@/api/request'
import { typeLabel } from '@/utils/status'
import StatusTag from '@/components/StatusTag.vue'
import UrgencyTag from '@/components/UrgencyTag.vue'

const router = useRouter()
const poolLoading = ref(false)
const mineLoading = ref(false)
const poolRows = ref<DemandRow[]>([])
const poolTotal = ref(0)
const poolQuery = reactive({ page: 1, size: 10 })
const mineRows = ref<DemandRow[]>([])
const mineTotal = ref(0)
const mineQuery = reactive({ page: 1, size: 10, status: '' })

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function loadPool(page = poolQuery.page) {
  poolQuery.page = page
  poolLoading.value = true
  try {
    const data = await triageApi.pool({ page: poolQuery.page, size: poolQuery.size })
    poolRows.value = data.records
    poolTotal.value = data.total
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    poolLoading.value = false
  }
}

async function loadMine(page = mineQuery.page) {
  mineQuery.page = page
  mineLoading.value = true
  try {
    const data = await triageApi.mine({
      page: mineQuery.page, size: mineQuery.size, status: mineQuery.status || undefined,
    })
    mineRows.value = data.records
    mineTotal.value = data.total
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    mineLoading.value = false
  }
}

async function reload() {
  await Promise.all([loadPool(), loadMine()])
}

function goDetail(row: DemandRow) {
  router.push(`/demands/${row.id}`)
}

function goSolution(row: DemandRow) {
  router.push({ path: `/demands/${row.id}`, query: { tab: 'solution' } })
}

async function claim(row: DemandRow) {
  try {
    await triageApi.claim(row.id)
    ElMessage.success(`已领取 ${row.demandNo}`)
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '领取失败'))
    await reload() // 被他人抢先（1208）时刷新列表口径
  }
}

async function start(row: DemandRow) {
  try {
    await flowApi.start(row.id)
    ElMessage.success('已开始处理')
    await loadMine()
  } catch (e) {
    ElMessage.error(errorMessage(e, '操作失败'))
  }
}

/** 需要填原因的动作统一走 prompt（挂起/退单） */
async function promptReason(title: string, placeholder: string): Promise<string | null> {
  try {
    const { value } = await ElMessageBox.prompt(placeholder, title, {
      inputPlaceholder: placeholder,
      inputValidator: (v: string) => (v && v.trim() ? true : '原因必填'),
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    return (value as string).trim()
  } catch {
    return null
  }
}

async function hold(row: DemandRow) {
  const reason = await promptReason(`挂起：${row.demandNo}`, '请填写挂起原因（如等待业务方确认）')
  if (!reason) return
  try {
    await flowApi.hold(row.id, reason)
    ElMessage.success('已挂起')
    await loadMine()
  } catch (e) {
    ElMessage.error(errorMessage(e, '挂起失败'))
  }
}

async function resume(row: DemandRow) {
  try {
    await flowApi.resume(row.id)
    ElMessage.success('已恢复处理')
    await loadMine()
  } catch (e) {
    ElMessage.error(errorMessage(e, '恢复失败'))
  }
}

async function submitAcceptance(row: DemandRow) {
  try {
    await ElMessageBox.confirm(
      '提交验收前请确认：方案已通过评审、工时已填报、交付物已上传。确认提交？', '提交验收',
      { type: 'warning', confirmButtonText: '提交', cancelButtonText: '取消' })
  } catch { return }
  try {
    await flowApi.submitAcceptance(row.id)
    ElMessage.success('已提交验收，等待提报人验收')
    await loadMine()
  } catch (e) {
    ElMessage.error(errorMessage(e, '提交失败'))
  }
}

async function returnPool(row: DemandRow) {
  const reason = await promptReason(`退单：${row.demandNo}`, '请填写退单原因（退回处理池后由他人承接）')
  if (!reason) return
  try {
    await triageApi.returnPool(row.id, reason)
    ElMessage.success('已退回处理池')
    await reload()
  } catch (e) {
    ElMessage.error(errorMessage(e, '退单失败'))
  }
}

onMounted(() => {
  loadPool(1)
  loadMine(1)
})
</script>

<style scoped>
.page { display: flex; flex-direction: column; gap: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.pager { margin-top: 16px; justify-content: flex-end; }
:deep(.el-table__row) { cursor: pointer; }
</style>
