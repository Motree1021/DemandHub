<template>
  <div v-loading="loading">
    <div class="toolbar">
      <el-radio-group v-model="range" @change="onRangeChange">
        <el-radio-button value="week">本周</el-radio-button>
        <el-radio-button value="month">本月</el-radio-button>
        <el-radio-button value="quarter">本季度</el-radio-button>
        <el-radio-button value="custom">自定义</el-radio-button>
      </el-radio-group>
      <el-date-picker v-if="range === 'custom'" v-model="customDates" type="daterange"
                      value-format="YYYY-MM-DD" start-placeholder="开始日期" end-placeholder="结束日期"
                      @change="load" />
    </div>

    <el-row :gutter="12" class="kpi-row">
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">本月新增</div><div class="kpi-value">{{ board?.kpi.monthNew ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">在途需求</div><div class="kpi-value">{{ board?.kpi.inflight ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">范围内完成</div><div class="kpi-value">{{ board?.kpi.done ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">SLA 超时</div><div class="kpi-value danger">{{ board?.kpi.slaOver ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">平均交付周期</div><div class="kpi-value">{{ cycleText }}</div></el-card></el-col>
      <el-col :span="4">
        <el-card shadow="never">
          <div class="kpi-label">SLA 健康度</div>
          <div class="sla-health">
            <span class="ok">正常 {{ board?.slaHealth.normal ?? 0 }}</span>
            <span class="warn">预警 {{ board?.slaHealth.warn ?? 0 }}</span>
            <span class="danger">超时 {{ board?.slaHealth.over ?? 0 }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="chart-card">
      <template #header>近 12 周趋势（提交 vs 完成）</template>
      <div ref="trendChart.el" class="chart" />
    </el-card>

    <el-row :gutter="12">
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header>类型分布</template>
          <div ref="typeChart.el" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header>渠道分布</template>
          <div ref="channelChart.el" class="chart" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" class="chart-card">
          <template #header>部门在途 Top10</template>
          <div ref="deptChart.el" class="chart" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { dashboardApi } from '@/api'
import type { BoardRange, ManagerBoard } from '@/api'
import { useChart } from '@/utils/useChart'

const range = ref<BoardRange>('month')
const customDates = ref<[string, string] | null>(null)
const board = ref<ManagerBoard>()
const loading = ref(false)
const trendChart = useChart()
const typeChart = useChart()
const channelChart = useChart()
const deptChart = useChart()

const cycleText = computed(() =>
  board.value?.kpi.avgCycleHours == null ? '-' : `${board.value.kpi.avgCycleHours} 小时`)

function onRangeChange() {
  if (range.value !== 'custom') load()
}

async function load() {
  if (range.value === 'custom' && !customDates.value?.[0]) return
  loading.value = true
  try {
    const query = range.value === 'custom'
      ? { range: range.value, from: customDates.value![0], to: customDates.value![1] }
      : { range: range.value }
    board.value = await dashboardApi.manager(query)
    renderCharts()
  } catch (error) {
    ElMessage.error((error as Error).message || '看板加载失败')
  } finally {
    loading.value = false
  }
}

function renderCharts() {
  const data = board.value
  if (!data) return
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['新提交', '完成'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: data.trend.map(t => t.weekStart.slice(5)) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '新提交', type: 'line', smooth: true, data: data.trend.map(t => t.newCnt) },
      { name: '完成', type: 'line', smooth: true, data: data.trend.map(t => t.doneCnt) },
    ],
  })
  const pie = (items: { name: string; value: number }[]) => ({
    tooltip: { trigger: 'item' },
    series: [{ type: 'pie', radius: ['40%', '70%'], data: items,
               label: { formatter: '{b}: {c}' } }],
  })
  typeChart.setOption(pie(data.typeDistribution.map(t => ({ name: t.typeCode, value: t.cnt }))))
  channelChart.setOption(pie(data.channelDistribution.map(c => ({ name: c.channel, value: c.cnt }))))
  deptChart.setOption({
    tooltip: {},
    grid: { left: 80, right: 20, top: 10, bottom: 30 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: data.deptBacklog.map(d => d.dept).reverse() },
    series: [{ type: 'bar', data: data.deptBacklog.map(d => d.cnt).reverse(),
               itemStyle: { color: '#409eff' } }],
  })
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
.kpi-row { margin-bottom: 12px; }
.kpi-label { color: #909399; font-size: 13px; }
.kpi-value { font-size: 26px; font-weight: 600; margin-top: 6px; }
.kpi-value.danger, .danger { color: #f56c6c; }
.ok { color: #67c23a; }
.warn { color: #e6a23c; }
.sla-health { display: flex; gap: 10px; margin-top: 10px; font-size: 13px; }
.chart-card { margin-bottom: 12px; }
.chart { height: 300px; }
</style>
