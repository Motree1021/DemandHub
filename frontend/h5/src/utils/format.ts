export function statusLabel(status: string | null | undefined): string {
  return ({ DRAFT: '草稿', SUBMITTED: '已提交', CLOSED: '已撤销' } as Record<string, string>)[status || ''] || status || '未知'
}
export function typeLabel(type: string | null | undefined): string {
  return ({ TECH: '科技需求', MATL: '物料需求', TRAIN: '培训需求' } as Record<string, string>)[type || ''] || type || '类型待确认'
}
export function urgencyLabel(urgency: string | null | undefined): string {
  return ({ NORMAL: '普通', URGENT: '紧急', CRITICAL: '特急' } as Record<string, string>)[urgency || ''] || urgency || '普通'
}
export function fmtTime(time: string | null | undefined): string { return time ? time.replace('T', ' ').slice(0, 16) : '未记录' }
