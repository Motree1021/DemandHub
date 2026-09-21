/** 状态/紧急程度/动作等展示元数据与时间格式化工具 */

export interface TagMeta {
  label: string
  type: 'primary' | 'success' | 'warning' | 'danger' | 'info'
}

/** 需求主状态展示（与后端 DemandStatus 一致） */
export const STATUS_META: Record<string, TagMeta> = {
  DRAFT: { label: '草稿', type: 'info' },
  SUBMITTED: { label: '待受理', type: 'primary' },
  NEED_INFO: { label: '待补充', type: 'warning' },
  TRIAGE: { label: '待分派/待领取', type: 'primary' },
  ANALYZING: { label: '分析中', type: 'primary' },
  SOLUTION_REVIEW: { label: '方案待评审', type: 'warning' },
  CONFIRMED: { label: '已确认/已排期', type: 'primary' },
  IN_PROGRESS: { label: '处理中', type: 'primary' },
  ACCEPTANCE: { label: '待验收', type: 'warning' },
  DONE: { label: '已完成', type: 'success' },
  CLOSED: { label: '已关闭', type: 'info' }
}

export function statusLabel(status: string | null | undefined): string {
  return (status && STATUS_META[status]?.label) || status || '-'
}

export function statusTagType(status: string | null | undefined): TagMeta['type'] {
  return (status && STATUS_META[status]?.type) || 'info'
}

/** 紧急程度 */
export const URGENCY_META: Record<string, TagMeta> = {
  NORMAL: { label: '普通', type: 'info' },
  URGENT: { label: '紧急', type: 'warning' },
  CRITICAL: { label: '特急', type: 'danger' }
}

export function urgencyLabel(u: string | null | undefined): string {
  return (u && URGENCY_META[u]?.label) || u || '-'
}

export function urgencyTagType(u: string | null | undefined): TagMeta['type'] {
  return (u && URGENCY_META[u]?.type) || 'info'
}

/** 类型编码兜底展示（接口拿不到名称时用） */
export const TYPE_LABELS: Record<string, string> = {
  TECH: '科技需求',
  MATL: '物料需求',
  TRAIN: '培训需求'
}

export function typeLabel(code: string | null | undefined, typeName?: string | null): string {
  return typeName || (code && TYPE_LABELS[code]) || code || '-'
}

/** 流转动作展示（与后端 DemandEvent 一致） */
export const EVENT_LABELS: Record<string, string> = {
  SUBMIT: '提交需求',
  WITHDRAW: '提报人撤销',
  ACCEPT: '经理受理',
  RETURN: '退回补充',
  CLOSE: '关闭',
  ASSIGN: '经理分派',
  CLAIM: '处理人领取',
  CHANGE_TYPE: '类型修正',
  SUBMIT_REVIEW: '提交方案评审',
  REVIEW_PASS: '评审通过',
  REVIEW_REJECT: '评审打回',
  START: '开始处理',
  SUBMIT_ACCEPTANCE: '提交验收',
  ACCEPT_PASS: '验收通过',
  ACCEPT_REJECT: '验收打回',
  HOLD: '挂起',
  RESUME: '恢复'
}

export function eventLabel(action: string | null | undefined): string {
  return (action && EVENT_LABELS[action]) || action || '-'
}

/** 关联类型 */
export const RELATION_LABELS: Record<string, string> = {
  PARENT: '父子',
  DEPENDS: '依赖',
  DUPLICATE: '重复',
  SPLIT: '拆分'
}

/** 方案状态 */
export const SOLUTION_STATUS_META: Record<string, TagMeta> = {
  DRAFT: { label: '草稿', type: 'info' },
  REVIEWING: { label: '评审中', type: 'warning' },
  APPROVED: { label: '已通过', type: 'success' },
  REJECTED: { label: '已打回', type: 'danger' }
}

/** 时间格式化：后端 ISO（2026-09-21T07:42:27.084）-> 友好显示（2026-09-21 07:42） */
export function fmtTime(t: string | null | undefined, withSeconds = false): string {
  if (!t) {
    return '-'
  }
  const normalized = t.replace('T', ' ')
  return withSeconds ? normalized.slice(0, 19) : normalized.slice(0, 16)
}

export function fmtDate(t: string | null | undefined): string {
  if (!t) {
    return '-'
  }
  return t.slice(0, 10)
}

/** 文件大小 */
export function fmtSize(bytes: number | null | undefined): string {
  if (!bytes && bytes !== 0) {
    return '-'
  }
  if (bytes < 1024) {
    return `${bytes} B`
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 停留时长（分钟 -> 友好） */
export function fmtMinutes(minutes: number | null | undefined): string {
  if (minutes == null) {
    return '-'
  }
  if (minutes < 60) {
    return `${minutes} 分钟`
  }
  if (minutes < 60 * 24) {
    return `${Math.floor(minutes / 60)} 小时`
  }
  return `${Math.floor(minutes / 60 / 24)} 天 ${Math.floor((minutes % (60 * 24)) / 60)} 小时`
}
