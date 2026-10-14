<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="exportVisible = true">新建导出</el-button>
      <span class="tip">导出生成后可在此下载；生成完成会通过站内信提醒你。</span>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="taskNo" label="任务号" width="180" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ statusLabelOf(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="fileName" label="文件名" min-width="200">
          <template #default="{ row }">{{ row.fileName || '—' }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <span v-if="row.status === 'FAILED'" class="error">{{ row.errorMsg }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="createdAt" label="创建时间" width="170" />
        <el-table-column prop="finishedAt" label="完成时间" width="170">
          <template #default="{ row }">{{ row.finishedAt || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'SUCCESS'" link type="primary" @click="onDownload(row)">
              下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                     :page-size="size" :current-page="current" @current-change="load" />
    </el-card>

    <el-dialog v-model="exportVisible" title="新建需求清单导出" width="520px">
      <el-form label-width="90px">
        <el-form-item label="状态">
          <el-select v-model="form.status" clearable placeholder="全部状态" style="width: 100%">
            <el-option v-for="s in FLOW_STATUS_OPTIONS" :key="s" :label="statusLabel(s)" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.demandTypeCode" clearable placeholder="全部类型" style="width: 100%">
            <el-option v-for="(label, code) in TYPE_META" :key="code" :label="label" :value="code" />
          </el-select>
        </el-form-item>
        <el-form-item label="紧急度">
          <el-select v-model="form.urgency" clearable placeholder="全部" style="width: 100%">
            <el-option v-for="(meta, code) in URGENCY_META" :key="code" :label="meta.label" :value="code" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键字">
          <el-input v-model="form.keyword" placeholder="按标题模糊搜索" clearable />
        </el-form-item>
        <el-form-item label="提交时间">
          <el-date-picker v-model="form.dates" type="daterange" value-format="YYYY-MM-DD"
                          start-placeholder="开始日期" end-placeholder="结束日期" style="width: 100%" />
        </el-form-item>
        <el-form-item label="范围">
          <el-checkbox v-model="form.mine">只看我提报的</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="exportVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onExport">开始导出</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import type { ReportExportParams } from '@/api'

export interface ExportFormState {
  status: string; demandTypeCode: string; urgency: string; keyword: string
  dates: [string, string] | null; mine: boolean
}

/** 表单 → 导出参数：空值剔除；结束日期 +1 天（后端 submittedTo 为排他右边界 [from, to)）。 */
export function toExportParams(form: ExportFormState): ReportExportParams {
  let submittedTo: string | undefined
  if (form.dates?.[1]) {
    const d = new Date(`${form.dates[1]}T00:00:00`)
    d.setDate(d.getDate() + 1)
    // 本地时区拼串（toISOString 会转 UTC，+8 时区下日期回拨一天）
    const pad = (n: number) => String(n).padStart(2, '0')
    submittedTo = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  }
  return {
    status: form.status || undefined,
    demandTypeCode: form.demandTypeCode || undefined,
    urgency: form.urgency || undefined,
    keyword: form.keyword || undefined,
    submittedFrom: form.dates?.[0],
    submittedTo,
    mine: form.mine || undefined,
  }
}
</script>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { reportApi } from '@/api'
import type { ReportTaskRow } from '@/api'
import { downloadFile } from '@/api/request'
import { FLOW_STATUS_OPTIONS, TYPE_META, URGENCY_META, statusLabel } from '@/utils/status'

const TASK_STATUS: Record<string, { label: string; type: 'info' | 'warning' | 'success' | 'danger' }> = {
  PENDING: { label: '排队中', type: 'info' },
  RUNNING: { label: '生成中', type: 'warning' },
  SUCCESS: { label: '已完成', type: 'success' },
  FAILED: { label: '失败', type: 'danger' },
}
const statusLabelOf = (status: string) => TASK_STATUS[status]?.label || status
const statusTag = (status: string) => TASK_STATUS[status]?.type || 'info'

const rows = ref<ReportTaskRow[]>([])
const total = ref(0)
const current = ref(1)
const size = 10
const loading = ref(false)
const exportVisible = ref(false)
const submitting = ref(false)
const form = reactive({
  status: '', demandTypeCode: '', urgency: '', keyword: '',
  dates: null as [string, string] | null, mine: false,
})

async function load(page = current.value) {
  loading.value = true
  try {
    const data = await reportApi.tasks({ current: page, size })
    rows.value = data.records
    total.value = data.total
    current.value = page
  } finally {
    loading.value = false
  }
}

async function onExport() {
  submitting.value = true
  try {
    await reportApi.export(toExportParams(form))
    ElMessage.success('导出任务已创建，生成完成后可下载')
    exportVisible.value = false
    await load(1)
  } catch (error) {
    ElMessage.error((error as Error).message || '创建导出失败')
  } finally {
    submitting.value = false
  }
}

async function onDownload(row: ReportTaskRow) {
  await downloadFile(reportApi.downloadPath(row.id), row.fileName || `${row.taskNo}.xlsx`)
}

// 有排队/生成中任务时 3s 轮询直到全部落地
let timer: ReturnType<typeof setInterval> | undefined
function armPolling() {
  clearInterval(timer)
  timer = setInterval(async () => {
    if (rows.value.some(r => r.status === 'PENDING' || r.status === 'RUNNING')) await load()
  }, 3000)
}

onMounted(async () => {
  await load(1)
  armPolling()
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
.error { color: #f56c6c; font-size: 13px; }
.pager { margin-top: 12px; justify-content: flex-end; }
</style>
