/** 状态/紧急程度/动作等展示元数据与时间格式化工具（移动端色值对齐原型） */

export interface ColorMeta {
  label: string
  /** 标签背景色 */
  bg: string
  /** 标签文字色 */
  color: string
}

/** 需求主状态展示（与后端 DemandStatus 一致，色值对齐移动端原型） */
export const STATUS_META: Record<string, ColorMeta> = {
  DRAFT: { label: '草稿', bg: '#f3f4f6', color: '#6b7280' },
  SUBMITTED: { label: '待受理', bg: '#eef3fb', color: '#1a3a6b' },
  NEED_INFO: { label: '待补充', bg: '#fef3c7', color: '#b45309' },
  TRIAGE: { label: '待分派/待领取', bg: '#eef3fb', color: '#1a3a6b' },
  ANALYZING: { label: '分析中', bg: '#fef3c7', color: '#b45309' },
  SOLUTION_REVIEW: { label: '方案待评审', bg: '#fef3c7', color: '#b45309' },
  CONFIRMED: { label: '已确认/已排期', bg: '#eef3fb', color: '#1a3a6b' },
  IN_PROGRESS: { label: '处理中', bg: '#d1fae5', color: '#065f46' },
  ACCEPTANCE: { label: '待验收', bg: '#fef3c7', color: '#b45309' },
  DONE: { label: '已完成', bg: '#f3f4f6', color: '#6b7280' },
  CLOSED: { label: '已关闭', bg: '#f3f4f6', color: '#6b7280' }
}

export function statusLabel(status: string | null | undefined): string {
  return (status && STATUS_META[status]?.label) || status || '-'
}

export function statusMeta(status: string | null | undefined): ColorMeta {
  return (status && STATUS_META[status]) || { label: status || '-', bg: '#f3f4f6', color: '#6b7280' }
}

/** 紧急程度 */
export const URGENCY_META: Record<string, ColorMeta> = {
  NORMAL: { label: '普通', bg: '#f3f4f6', color: '#6b7280' },
  URGENT: { label: '紧急', bg: '#fff0f0', color: '#ff4757' },
  CRITICAL: { label: '特急', bg: '#ff4757', color: '#ffffff' }
}

export function urgencyLabel(u: string | null | undefined): string {
  return (u && URGENCY_META[u]?.label) || u || '-'
}

export function urgencyMeta(u: string | null | undefined): ColorMeta {
  return (u && URGENCY_META[u]) || { label: u || '-', bg: '#f3f4f6', color: '#6b7280' }
}

/** 类型编码兜底展示（接口拿不到名称时用），色值对齐原型 dt-tech/dt-matl/dt-train */
export const TYPE_META: Record<string, ColorMeta & { icon: string; short: string }> = {
  TECH: { label: '科技需求', short: '科技', icon: '🔧', bg: '#dbeafe', color: '#1d4ed8' },
  MATL: { label: '物料需求', short: '物料', icon: '📦', bg: '#fce7f3', color: '#be185d' },
  TRAIN: { label: '培训需求', short: '培训', icon: '🎓', bg: '#d1fae5', color: '#047857' }
}

export function typeLabel(code: string | null | undefined, typeName?: string | null): string {
  return typeName || (code && TYPE_META[code]?.label) || code || '-'
}

export function typeShortLabel(code: string | null | undefined, typeName?: string | null): string {
  if (code && TYPE_META[code]) {
    return TYPE_META[code].short
  }
  return typeName || code || '-'
}

export function typeMeta(code: string | null | undefined): ColorMeta & { icon: string; short: string } {
  return (code && TYPE_META[code]) || { label: code || '-', short: code || '-', icon: '📄', bg: '#f3f4f6', color: '#6b7280' }
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

/** 扩展字段中文标签（详情页按类型渲染） */
export const EXT_FIELD_LABELS: Record<string, string> = {
  relatedSystem: '关联系统',
  relatedModule: '关联模块',
  businessScenario: '业务场景',
  acceptanceCriteria: '验收标准',
  materialSubtype: '物料子类',
  usageScenario: '使用场景',
  quantity: '数量',
  expectedArrivalAt: '期望到位时间',
  trainingSubtype: '培训子类',
  traineeObject: '培训对象',
  traineeCount: '培训人数',
  expectedCompleteAt: '期望完成时间'
}
