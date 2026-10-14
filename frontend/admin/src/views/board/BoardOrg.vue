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
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">待受理</div><div class="kpi-value">{{ board?.pendingAccept ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">处理池</div><div class="kpi-value">{{ board?.pool ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">处理中</div><div class="kpi-value">{{ board?.processing ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">本周完成</div><div class="kpi-value ok">{{ board?.weekDone ?? '-' }}</div></el-card></el-col>
      <el-col :span="4"><el-card shadow="never"><div class="kpi-label">人均在途</div><div class="kpi-value">{{ board?.avgInflightPerHandler ?? '-' }}</div></el-card></el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>成员工作量（工时为所选范围内登记）</template>
      <el-table :data="board?.memberWorkload || []">
        <el-table-column prop="userName" label="成员" width="160" />
        <el-table-column prop="inflightCnt" label="在途需求" width="120" sortable />
        <el-table-column prop="effortHours" label="工时（小时）" sortable />
      </el-table>
      <el-empty v-if="board && !board.memberWorkload.length" description="暂无处理人数据" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { dashboardApi } from '@/api'
import type { BoardRange, OrgBoard } from '@/api'

const range = ref<BoardRange>('month')
const customDates = ref<[string, string] | null>(null)
const board = ref<OrgBoard>()
const loading = ref(false)

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
    board.value = await dashboardApi.org(query)
  } catch (error) {
    ElMessage.error((error as Error).message || '看板加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 12px; }
.kpi-row { margin-bottom: 12px; }
.kpi-label { color: #909399; font-size: 13px; }
.kpi-value { font-size: 26px; font-weight: 600; margin-top: 6px; }
.kpi-value.ok { color: #67c23a; }
</style>
