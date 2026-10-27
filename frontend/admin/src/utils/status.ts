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

/** 需求层级四分类（2026-10-22 拍板）：口径优先——轻量提报（ext.mode.level='light'）一律「微需求」；
 *  常规口径再按判型分业务/用户/功能。判型口径（2026-10-26 拍板派生制）与 H5 recognitionLevelOf 完全一致：
 *  confirmed 人工确认优先；新结构 level 直读（服务端按表单素材派生）；旧票数结构兼容折算——
 *  business≥0.7→业务需求，user≥0.7→用户需求，其余→功能需求。
 *  无判型数据（老数据/未走 AI 流程）返回 null，列表显示「—」。 */
export type DemandLevel = 'business' | 'user' | 'function' | 'micro'

export const DEMAND_LEVEL_META: Record<DemandLevel, { label: string; type: TagType }> = {
  business: { label: '业务需求', type: 'danger' },
  user: { label: '用户需求', type: 'warning' },
  function: { label: '功能需求', type: 'primary' },
  micro: { label: '微需求', type: 'success' },
}

export function demandLevelOf(ext: Record<string, unknown> | null | undefined): DemandLevel | null {
  if (!ext) return null
  const mode = ext.mode as { level?: string } | undefined
  if (mode?.level === 'light') return 'micro'
  const recognition = ext.typeRecognition as {
    confirmed?: string | null; level?: string; business?: number; user?: number; function?: number
  } | undefined
  if (!recognition) return null
  const confirmed = recognition.confirmed
  if (confirmed === 'business' || confirmed === 'user' || confirmed === 'function') return confirmed
  const level = recognition.level
  if (level === 'business' || level === 'user' || level === 'function') return level
  // 旧票数结构兼容折算（2026-10-26 派生制改造前存量数据）
  const business = recognition.business ?? 0
  const user = recognition.user ?? 0
  if (business >= 0.7) return 'business'
  return user >= 0.7 ? 'user' : 'function'
}

export const RELATION_TYPE_META: Record<string, string> = {
  PARENT: '父子',
  DEPENDS: '依赖',
  DUPLICATE: '重复',
  SPLIT: '拆分',
}
