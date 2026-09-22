import { get, post } from './request'
import service from './request'

/** 管理者看板（M6） */
export interface ManagerBoard {
  kpi: {
    monthNew: number
    inflight: number
    done: number
    slaOver: number
    avgCycleHours: number | null
  }
  trend: { weekStart: string; newCnt: number; doneCnt: number }[]
  typeDistribution: { typeCode: string; typeName: string; cnt: number }[]
  /** 渠道来源分布（channelName 由 demand_channel 注册表映射，如 创金零售） */
  channelDistribution: { channel: string; channelName: string; cnt: number }[]
  orgBacklog: { orgId: number; orgName: string; cnt: number }[]
  slaHealth: { normal: number; warn: number; over: number }
}

/** 经理看板（M6） */
export interface OrgBoard {
  pendingAccept: number
  pool: number
  processing: number
  weekDone: number
  avgInflightPerHandler: number | null
  memberWorkload: { userId: number; userName: string; inflightCnt: number; effortHours: number }[]
}

export type BoardRange = 'week' | 'month' | 'quarter' | 'custom'

export function managerBoard(range: BoardRange, from?: string, to?: string): Promise<ManagerBoard> {
  return get('/demand/dashboard/manager', { range, from, to })
}

export function orgBoard(): Promise<OrgBoard> {
  return get('/demand/dashboard/org')
}

/** 手动触发预聚合刷新（ADMIN/EXECUTIVE） */
export function refreshStatDaily(): Promise<{ affectedRows: number }> {
  return post('/demand/dashboard/stat-refresh')
}

/* ---------------- 报表异步导出 ---------------- */

export interface ReportExportParams {
  reportType?: string
  status?: string
  demandTypeCode?: string
  urgency?: string
  keyword?: string
  mine?: boolean
  submittedFrom?: string
  submittedTo?: string
}

export interface ReportTask {
  id: number
  taskNo: string
  reportType: string
  paramsJson: string | null
  requesterId: number
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'
  filePath: string | null
  fileName: string | null
  errorMsg: string | null
  createdAt: string
  finishedAt: string | null
}

export function createReportExport(params: ReportExportParams): Promise<ReportTask> {
  return post('/demand/report/export', params)
}

export function myReportTasks(limit = 20): Promise<ReportTask[]> {
  return get('/demand/report/tasks', { limit })
}

/** 下载导出文件（blob 拉取，经网关鉴权） */
export async function downloadReport(taskId: number, fileName: string): Promise<void> {
  const resp = await service.get(`/demand/report/download/${taskId}`, { responseType: 'blob' })
  const blob = resp.data as Blob
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName || 'report.xlsx'
  a.click()
  window.URL.revokeObjectURL(url)
}
