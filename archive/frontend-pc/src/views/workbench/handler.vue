<template>
  <div class="handler-page">
    <!-- 待领取池 -->
    <el-card shadow="never" class="mb16">
      <template #header>待领取需求池（本组织 TRIAGE）</template>
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
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="onClaim(row)">领取</el-button>
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

    <!-- 我的待办（我处理中的需求） -->
    <el-card shadow="never" class="mb16">
      <template #header>我的待办（处理中）</template>
      <el-table :data="todo" v-loading="todoLoading" border>
        <el-table-column label="编号" width="165">
          <template #default="{ row }">
            <el-link type="primary" @click="goDetail(row.id)">{{ row.demandNo }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ typeLabel(row.demandTypeCode, row.typeName) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="紧急" width="80">
          <template #default="{ row }">
            <el-tag :type="urgencyTagType(row.urgency)" size="small">{{ urgencyLabel(row.urgency) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期望交付" width="110">
          <template #default="{ row }">{{ fmtDate(row.expectDeliveryAt) }}</template>
        </el-table-column>
        <el-table-column label="提交时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.submittedAt) }}</template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="todoTotal"
        :page-size="todoQuery.size"
        :current-page="todoQuery.current"
        @current-change="loadTodo"
      />
    </el-card>

    <!-- 我的工时统计 -->
    <el-card shadow="never">
      <template #header>我的工时统计（近 30 天填报）</template>
      <el-empty v-if="!myEfforts.length" description="暂无工时记录，去需求详情页填报" :image-size="60" />
      <template v-else>
        <div class="effort-total">
          累计 <b>{{ totalHours }}</b> 小时
        </div>
        <el-table :data="myEfforts" size="small" border max-height="320">
          <el-table-column label="日期" width="110">
            <template #default="{ row }">{{ fmtDate(row.workDate) }}</template>
          </el-table-column>
          <el-table-column label="需求" min-width="180">
            <template #default="{ row }">
              <el-link type="primary" @click="goDetail(row.demandId)">{{ demandNoOf(row.demandId) }}</el-link>
            </template>
          </el-table-column>
          <el-table-column prop="hours" label="工时(h)" width="90" />
          <el-table-column prop="description" label="工作内容" min-width="200" show-overflow-tooltip />
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  triagePool,
  claimDemand,
  pageDemands,
  listEfforts,
  getDemand,
  type DemandEntity,
  type DemandListItem,
  type EffortItem
} from '@/api/demand'
import { urgencyLabel, urgencyTagType, statusLabel, statusTagType, typeLabel, fmtTime, fmtDate } from '@/utils/format'

const router = useRouter()

const pool = ref<DemandEntity[]>([])
const poolTotal = ref(0)
const poolLoading = ref(false)
const todo = ref<DemandListItem[]>([])
const todoTotal = ref(0)
const todoLoading = ref(false)
const myEfforts = ref<EffortItem[]>([])
const totalHours = ref(0)
const demandNos = ref<Map<number, string>>(new Map())

const poolQuery = reactive({ current: 1, size: 10 })
const todoQuery = reactive({ current: 1, size: 10 })

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

/** 我的待办：数据权限内分派给我的在途需求（列表接口按当前人过滤，处理人只能看到本组织；进一步按状态筛在途） */
async function loadTodo(page = todoQuery.current) {
  todoQuery.current = page
  todoLoading.value = true
  try {
    // 处理人在途状态集合：ANALYZING/SOLUTION_REVIEW/CONFIRMED/IN_PROGRESS
    // 后端单状态过滤，这里并发查后合并（简化：查 IN_PROGRESS 为主，兼顾分析中）
    const [analyzing, inProgress, solutionReview, confirmed] = await Promise.all([
      pageDemands({ current: 1, size: 50, status: 'ANALYZING' }),
      pageDemands({ current: 1, size: 50, status: 'IN_PROGRESS' }),
      pageDemands({ current: 1, size: 50, status: 'SOLUTION_REVIEW' }),
      pageDemands({ current: 1, size: 50, status: 'CONFIRMED' })
    ])
    const merged = [...analyzing.records, ...inProgress.records, ...solutionReview.records, ...confirmed.records]
      // 只保留分派给我的
      .filter((d) => d.assigneeUserId != null)
      .sort((a, b) => (b.submittedAt || '').localeCompare(a.submittedAt || ''))
    // 前端分页
    todoTotal.value = merged.length
    const start = (todoQuery.current - 1) * todoQuery.size
    todo.value = merged.slice(start, start + todoQuery.size)
    // 顺手缓存编号用于工时表展示
    merged.forEach((d) => demandNos.value.set(d.id, d.demandNo))
  } finally {
    todoLoading.value = false
  }
}

/** 我的工时：遍历我的待办+已完成需求拉工时（数据量小，前端聚合） */
async function loadMyEfforts() {
  const done = await pageDemands({ current: 1, size: 50, status: 'DONE' })
  const ids = new Set<number>([...demandNos.value.keys()])
  done.records.forEach((d) => {
    ids.add(d.id)
    demandNos.value.set(d.id, d.demandNo)
  })
  const all: EffortItem[] = []
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400_000).toISOString().slice(0, 10)
  for (const id of ids) {
    try {
      const efforts = await listEfforts(id)
      all.push(...efforts.filter((e) => e.workDate >= thirtyDaysAgo))
    } catch {
      // 无权限或不存在则跳过
    }
  }
  all.sort((a, b) => b.workDate.localeCompare(a.workDate))
  myEfforts.value = all
  totalHours.value = all.reduce((sum, e) => sum + Number(e.hours || 0), 0)
}

function demandNoOf(id: number): string {
  return demandNos.value.get(id) || `#${id}`
}

async function onClaim(row: DemandEntity) {
  await ElMessageBox.confirm(`确认领取 ${row.demandNo}？领取后进入分析阶段。`, '领取确认', { type: 'info' })
  await claimDemand(row.id)
  ElMessage.success('领取成功')
  loadPool()
  loadTodo()
}

function goDetail(id: number) {
  router.push(`/demand/detail/${id}`)
}

onMounted(async () => {
  await Promise.all([loadPool(1), loadTodo(1)])
  loadMyEfforts()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.pager {
  margin-top: 12px;
  justify-content: flex-end;
}

.effort-total {
  margin-bottom: 10px;
  font-size: 14px;
}
</style>
