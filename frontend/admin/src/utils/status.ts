/** 需求状态/紧急度/类型的展示元数据（与后端 12 态状态机口径一致）。 */

export type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

export const STATUS_META: Record<string, { label: string; type: TagType }> = {
  DRAFT: { label: '草稿', type: 'info' },
  SUBMITTED: { label: '待受理', type: 'warning' },
  NEED_INFO: { label: '待补充', type: 'warning' },
  TRIAGE: { label: '待分派', type: 'primary' },
  ANALYZING: { label: '分析中', type: 'primary' },
  SOLUTION_REVIEW: { label: '方案待评审', type: 'primary' },
  CONFIRMED: { label: '已确认', type: 'primary' },
  IN_PROGRESS: { label: '处理中', type: 'primary' },
  ACCEPTANCE: { label: '待验收', type: 'warning' },
  DONE: { label: '已完成', type: 'success' },
  CLOSED: { label: '已关闭', type: 'info' },
}

/** 管理视角可见的流转态（草稿/待补充为提报人私有编辑态，不入列表筛选） */
export const FLOW_STATUS_OPTIONS = [
  'SUBMITTED', 'TRIAGE', 'ANALYZING', 'SOLUTION_REVIEW', 'CONFIRMED',
  'IN_PROGRESS', 'ACCEPTANCE', 'DONE', 'CLOSED',
]

export function statusLabel(status: string | null | undefined): string {
  return (status && STATUS_META[status]?.label) || status || '—'
}

export const URGENCY_META: Record<string, { label: string; type: TagType }> = {
  NORMAL: { label: '普通', type: 'info' },
  URGENT: { label: '紧急', type: 'warning' },
  CRITICAL: { label: '特急', type: 'danger' },
}

export const TYPE_META: Record<string, string> = {
  TECH: '科技需求',
  MATL: '物料需求',
  TRAIN: '培训需求',
}

export function typeLabel(code: string | null | undefined): string {
  return (code && TYPE_META[code]) || code || '—'
}

export const SOLUTION_STATUS_META: Record<string, { label: string; type: TagType }> = {
  DRAFT: { label: '草稿', type: 'info' },
  SUBMITTED: { label: '评审中', type: 'warning' },
  APPROVED: { label: '已通过', type: 'success' },
  REJECTED: { label: '已打回', type: 'danger' },
}

export const RELATION_TYPE_META: Record<string, string> = {
  PARENT: '父子',
  DEPENDS: '依赖',
  DUPLICATE: '重复',
  SPLIT: '拆分',
}
