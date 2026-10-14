// 12 态状态机的提报人视角文案（P2）：状态词以「我的需求进展到哪一步」为口径
const STATUS_LABELS: Record<string, string> = {
  DRAFT: '草稿', SUBMITTED: '已提交', NEED_INFO: '待补充', TRIAGE: '已受理',
  ANALYZING: '分析中', SOLUTION_REVIEW: '方案评审中', CONFIRMED: '方案已确认',
  IN_PROGRESS: '处理中', ACCEPTANCE: '待验收', DONE: '已完成', CLOSED: '已撤销',
  ON_HOLD: '挂起',
}
export function statusLabel(status: string | null | undefined): string {
  return STATUS_LABELS[status || ''] || status || '未知'
}
export function typeLabel(type: string | null | undefined): string {
  return ({ TECH: '科技需求', MATL: '物料需求', TRAIN: '培训需求' } as Record<string, string>)[type || ''] || type || '类型待确认'
}
export function urgencyLabel(urgency: string | null | undefined): string {
  return ({ NORMAL: '普通', URGENT: '紧急', CRITICAL: '特急' } as Record<string, string>)[urgency || ''] || urgency || '普通'
}
export function fmtTime(time: string | null | undefined): string { return time ? time.replace('T', ' ').slice(0, 16) : '未记录' }
