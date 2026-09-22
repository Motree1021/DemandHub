<template>
  <div class="board-page">
    <!-- 顶部工具条 -->
    <div class="toolbar">
      <el-radio-group v-model="range" @change="loadManager">
        <el-radio-button value="week">本周</el-radio-button>
        <el-radio-button value="month">本月</el-radio-button>
        <el-radio-button value="quarter">本季</el-radio-button>
      </el-radio-group>
      <div class="toolbar-right">
        <el-button v-if="canRefreshStat" :loading="refreshing" @click="onRefreshStat">刷新预聚合</el-button>
        <el-button type="primary" @click="exportDialog = true">导出报表</el-button>
        <el-button @click="taskDrawer = true">导出任务</el-button>
      </div>
    </div>

    <!-- KPI 卡片 -->
    <el-row :gutter="16" class="mb16" v-loading="loading">
      <el-col v-for="card in kpiCards" :key="card.label" :span="4">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">{{ card.label }}</div>
          <div class="kpi-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="kpi-sub">{{ card.sub }}</div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="never" class="kpi-card">
          <div class="kpi-label">SLA 健康度</div>
          <div class="sla-mini">
            <span class="sla-dot normal" />{{ board?.slaHealth.normal ?? 0 }}
            <span class="sla-dot warn" />{{ board?.slaHealth.warn ?? 0 }}
            <span class="sla-dot over" />{{ board?.slaHealth.over ?? 0 }}
          </div>
          <div class="kpi-sub">正常 / 预警 / 超期</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区 -->
    <el-row :gutter="16" class="mb16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>近 12 周新增 / 完成趋势</template>
          <div ref="trendRef" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>类型分布（{{ rangeLabel }}提交）</template>
          <div ref="typeRef" class="chart" />
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="16" class="mb16">
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>组织积压 Top 10（当前在途）</template>
          <div ref="backlogRef" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="7">
        <el-card shadow="never">
          <template #header>渠道来源分布（{{ rangeLabel }}提交）</template>
          <div ref="channelRef" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="7">
        <el-card shadow="never">
          <template #header>SLA 健康度分布</template>
          <div ref="slaRef" class="chart" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 经理看板（本组织） -->
    <template v-if="isManager && org">
      <el-divider content-position="left">本组织看板</el-divider>
      <el-row :gutter="16" class="mb16">
        <el-col :span="4">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">待受理</div>
            <div class="kpi-value" style="color: #d97706">{{ org.pendingAccept }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">需求池</div>
            <div class="kpi-value" style="color: #1d4ed8">{{ org.pool }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">处理中</div>
            <div class="kpi-value" style="color: #0d9488">{{ org.processing }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">本周完成</div>
            <div class="kpi-value" style="color: #16a34a">{{ org.weekDone }}</div>
          </el-card>
        </el-col>
        <el-col :span="4">
          <el-card shadow="never" class="kpi-card">
            <div class="kpi-label">人均在途</div>
            <div class="kpi-value">{{ org.avgInflightPerHandler ?? '-' }}</div>
          </el-card>
        </el-col>
      </el-row>
      <el-card shadow="never" class="mb16">
        <template #header>团队成员工作量（在途数 / 累计工时 h）</template>
        <el-table :data="org.memberWorkload" size="small">
          <el-table-column prop="userName" label="成员" width="140" />
          <el-table-column prop="inflightCnt" label="在途需求数" width="120" />
          <el-table-column prop="effortHours" label="累计工时（h）" width="140" />
          <el-table-column label="负荷">
            <template #default="{ row }">
              <el-progress
                :percentage="workloadPercent(row.inflightCnt)"
                :color="row.inflightCnt >= 8 ? '#dc2626' : row.inflightCnt >= 5 ? '#d97706' : '#16a34a'"
              />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!org.memberWorkload.length" description="暂无成员在途数据" :image-size="60" />
      </el-card>
    </template>

    <!-- 报表导出对话框 -->
    <el-dialog v-model="exportDialog" title="导出需求清单（异步生成，完成后站内信通知）" width="520px">
      <el-form :model="exportForm" label-width="90px">
        <el-form-item label="需求类型">
          <el-select v-model="exportForm.demandTypeCode" clearable placeholder="全部" style="width: 100%">
            <el-option v-for="t in typeList" :key="t.typeCode" :label="t.typeName" :value="t.typeCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="exportForm.status" clearable placeholder="全部" style="width: 100%">
            <el-option v-for="s in statusOptions" :key="s" :label="statusLabel(s)" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="exportForm.keyword" placeholder="标题 / 编号模糊" />
        </el-form-item>
        <el-form-item label="提交时间">
          <el-date-picker
            v-model="exportRange"
            type="daterange"
            value-format="YYYY-MM-DD"
            range-separator="至"
            start-placeholder="开始"
            end-placeholder="结束"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exportDialog = false">取消</el-button>
        <el-button type="primary" :loading="exporting" @click="onCreateExport">创建导出任务</el-button>
      </template>
    </el-dialog>

    <!-- 导出任务抽屉 -->
    <el-drawer v-model="taskDrawer" title="我的导出任务" size="480px">
      <el-button size="small" style="margin-bottom: 10px" @click="loadTasks">刷新</el-button>
      <el-empty v-if="!tasks.length" description="暂无导出任务" :image-size="60" />
      <div v-for="t in tasks" :key="t.id" class="task-item">
        <div class="task-head">
          <span class="task-no">{{ t.taskNo }}</span>
          <el-tag :type="taskTagType(t.status)" size="small">{{ taskStatusLabel(t.status) }}</el-tag>
        </div>
        <div class="muted">创建 {{ fmtTime(t.createdAt) }}<template v-if="t.finishedAt"> · 完成 {{ fmtTime(t.finishedAt) }}</template></div>
        <div v-if="t.status === 'FAILED'" class="task-err">{{ t.errorMsg }}</div>
        <div v-if="t.status === 'SUCCESS'" class="task-actions">
          <el-button size="small" type="primary" @click="downloadReport(t.id, t.fileName || 'report.xlsx')">下载 Excel</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import {
  managerBoard,
  orgBoard,
  refreshStatDaily,
  createReportExport,
  myReportTasks,
  downloadReport,
  type ManagerBoard,
  type OrgBoard,
  type BoardRange,
  type ReportTask
} from '@/api/board'
import { listActiveTypes, type DemandTypeItem } from '@/api/directory'
import { useUserStore } from '@/store/modules/user'
import { fmtTime, statusLabel } from '@/utils/format'

const userStore = useUserStore()
const route = useRoute()

const range = ref<BoardRange>('month')
const board = ref<ManagerBoard | null>(null)
const org = ref<OrgBoard | null>(null)
const loading = ref(false)
const refreshing = ref(false)

const isManager = computed(() => userStore.roles.includes('MANAGER'))
const canRefreshStat = computed(() => userStore.roles.includes('EXECUTIVE') || userStore.isAdmin)

const rangeLabel = computed(() => (range.value === 'week' ? '本周' : range.value === 'quarter' ? '本季' : '本月'))

const kpiCards = computed(() => {
  const k = board.value?.kpi
  return [
    { label: '本月新增', value: k?.monthNew ?? '-', sub: '自然月口径', color: '#1d4ed8' },
    { label: '当前在途', value: k?.inflight ?? '-', sub: '非终态需求', color: '#d97706' },
    { label: `${rangeLabel.value}完成`, value: k?.done ?? '-', sub: '按关闭时间', color: '#16a34a' },
    { label: '超 SLA', value: k?.slaOver ?? '-', sub: '红色告警', color: '#dc2626' },
    {
      label: '平均交付周期',
      value: k?.avgCycleHours != null ? `${k.avgCycleHours}h` : '-',
      sub: '提交 → 关闭',
      color: '#0d9488'
    }
  ]
})

/* ---------------- 图表 ---------------- */

const trendRef = ref<HTMLElement>()
const typeRef = ref<HTMLElement>()
const backlogRef = ref<HTMLElement>()
const channelRef = ref<HTMLElement>()
const slaRef = ref<HTMLElement>()
let charts: echarts.ECharts[] = []

function renderCharts() {
  if (!board.value) {
    return
  }
  charts.forEach((c) => c.dispose())
  charts = []
  const mk = (el: HTMLElement | undefined, option: echarts.EChartsOption) => {
    if (!el) {
      return
    }
    const chart = echarts.init(el)
    chart.setOption(option)
    charts.push(chart)
  }
  const b = board.value

  mk(trendRef.value, {
    tooltip: { trigger: 'axis' },
    legend: { data: ['新增', '完成'] },
    grid: { left: 40, right: 16, top: 36, bottom: 28 },
    xAxis: { type: 'category', data: b.trend.map((t) => t.weekStart.slice(5)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '新增', type: 'line', smooth: true, data: b.trend.map((t) => t.newCnt), areaStyle: { opacity: 0.12 }, color: '#1d4ed8' },
      { name: '完成', type: 'line', smooth: true, data: b.trend.map((t) => t.doneCnt), areaStyle: { opacity: 0.12 }, color: '#16a34a' }
    ]
  })

  mk(typeRef.value, {
    tooltip: { trigger: 'item', formatter: '{b}: {c}（{d}%）' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '44%'],
        label: { formatter: '{b}\n{c}' },
        data: b.typeDistribution.map((t) => ({ name: t.typeName || t.typeCode, value: t.cnt }))
      }
    ]
  })

  mk(backlogRef.value, {
    tooltip: { trigger: 'axis' },
    grid: { left: 110, right: 30, top: 10, bottom: 28 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: b.orgBacklog.map((o) => o.orgName).reverse() },
    series: [{ type: 'bar', data: b.orgBacklog.map((o) => o.cnt).reverse(), color: '#d97706', barMaxWidth: 18, label: { show: true, position: 'right' } }]
  })

  mk(channelRef.value, {
    tooltip: { trigger: 'item', formatter: '{b}: {c}（{d}%）' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '44%'],
        label: { formatter: '{b}\n{c}' },
        data: (b.channelDistribution || []).map((c) => ({ name: c.channelName || c.channel, value: c.cnt }))
      }
    ]
  })

  mk(slaRef.value, {
    tooltip: { trigger: 'item', formatter: '{b}: {c}（{d}%）' },
    legend: { bottom: 0 },
    series: [
      {
        type: 'pie',
        radius: ['38%', '62%'],
        center: ['50%', '44%'],
        data: [
          { name: '正常', value: b.slaHealth.normal, itemStyle: { color: '#16a34a' } },
          { name: '预警', value: b.slaHealth.warn, itemStyle: { color: '#d97706' } },
          { name: '超期', value: b.slaHealth.over, itemStyle: { color: '#dc2626' } }
        ]
      }
    ]
  })
}

function onResize() {
  charts.forEach((c) => c.resize())
}

/* ---------------- 数据加载 ---------------- */

async function loadManager() {
  loading.value = true
  try {
    board.value = await managerBoard(range.value)
    renderCharts()
  } finally {
    loading.value = false
  }
}

async function loadOrg() {
  if (!isManager.value) {
    return
  }
  try {
    org.value = await orgBoard()
  } catch {
    org.value = null
  }
}

async function onRefreshStat() {
  refreshing.value = true
  try {
    const r = await refreshStatDaily()
    ElMessage.success(`预聚合已刷新（${r.affectedRows} 行）`)
    loadManager()
  } finally {
    refreshing.value = false
  }
}

function workloadPercent(cnt: number): number {
  const max = Math.max(...(org.value?.memberWorkload.map((m) => m.inflightCnt) || [1]), 1)
  return Math.round((cnt / max) * 100)
}

/* ---------------- 报表导出 ---------------- */

const exportDialog = ref(false)
const exporting = ref(false)
const exportForm = reactive({ demandTypeCode: '', status: '', keyword: '' })
const exportRange = ref<[string, string] | null>(null)
const typeList = ref<DemandTypeItem[]>([])
const statusOptions = ['SUBMITTED', 'TRIAGE', 'ANALYZING', 'SOLUTION_REVIEW', 'IN_PROGRESS', 'ACCEPTANCE', 'DONE', 'CLOSED']

const taskDrawer = ref(false)
const tasks = ref<ReportTask[]>([])

async function onCreateExport() {
  exporting.value = true
  try {
    const task = await createReportExport({
      reportType: 'DEMAND_LIST',
      demandTypeCode: exportForm.demandTypeCode || undefined,
      status: exportForm.status || undefined,
      keyword: exportForm.keyword || undefined,
      submittedFrom: exportRange.value?.[0],
      submittedTo: exportRange.value?.[1]
    })
    ElMessage.success(`导出任务 ${task.taskNo} 已创建，完成后将通过站内信通知`)
    exportDialog.value = false
    loadTasks()
  } finally {
    exporting.value = false
  }
}

async function loadTasks() {
  tasks.value = await myReportTasks()
}

function taskStatusLabel(s: string): string {
  return { PENDING: '排队中', RUNNING: '生成中', SUCCESS: '已就绪', FAILED: '失败' }[s] || s
}

function taskTagType(s: string): 'info' | 'warning' | 'success' | 'danger' {
  return ({ PENDING: 'info', RUNNING: 'warning', SUCCESS: 'success', FAILED: 'danger' } as const)[s as 'PENDING'] || 'info'
}

onMounted(async () => {
  loadManager()
  loadOrg()
  loadTasks()
  // 站内信「报表已就绪」跳入：/board?tab=tasks 自动打开导出任务抽屉
  if (route.query.tab === 'tasks') {
    taskDrawer.value = true
  }
  typeList.value = await listActiveTypes()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  charts.forEach((c) => c.dispose())
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar-right {
  display: flex;
  gap: 8px;
}

.mb16 {
  margin-bottom: 16px;
}

.kpi-card {
  text-align: center;
}

.kpi-label {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.kpi-value {
  font-size: 26px;
  font-weight: 700;
  margin: 6px 0 2px;
}

.kpi-sub {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.sla-mini {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 18px;
  font-weight: 700;
  margin: 8px 0 4px;
}

.sla-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  margin-left: 8px;
}

.sla-dot.normal {
  background: #16a34a;
}

.sla-dot.warn {
  background: #d97706;
}

.sla-dot.over {
  background: #dc2626;
}

.chart {
  height: 300px;
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.task-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.task-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.task-no {
  font-weight: 600;
}

.task-err {
  color: var(--el-color-danger);
  font-size: 12px;
  margin-top: 4px;
}

.task-actions {
  margin-top: 8px;
}
</style>
