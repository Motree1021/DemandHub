import { get, post, put, del, downloadFile, fetchBlob, API_BASE, bearerHeaders } from './request'
export type FieldSources = Record<string, 'default' | 'agent' | 'user' | 'user_evidence'>
export interface ElementStatus { key: string; label?: string; status: 'OK' | 'VAGUE' | 'MISSING' | 'SKIP'; note: string; attempts: number }
export interface StandardField {
  key: string; label: string; path?: string | null; kind: 'text' | 'enum' | 'number' | 'date' | 'list'
  zone?: 'A' | 'B' | 'C' | 'D' | null; code?: string; system?: boolean
  options?: Record<string, string>; placeholder?: string; required?: boolean; default?: unknown
  okWhen?: string; example?: string; rule?: { minLen?: number; maxLen?: number }
}
export interface Standard {
  type: string; name: string; version: string; contentHash: string; elements: StandardField[]
  optionalFields: StandardField[]; commonFields: StandardField[]; subtypeFields: Record<string, StandardField[]>
  followUpOrder: string[]
}
export interface StandardSummary { code: string; name: string; description?: string }
export type ZoneElements = Record<string, Record<string, unknown>>
export interface DemandForm {
  title: string | null; demandTypeCode: string | null; content: string | null; urgency: string | null
  expectDeliveryAt: string | null; elements: ZoneElements; ext: Record<string, unknown>; fieldSources: FieldSources
}
export interface ChangeLog { id: number; fieldKey: string; oldValue: unknown; newValue: unknown; source: 'default' | 'agent' | 'user' | 'user_evidence'; changedBy: number | null; createdAt: string }
// 判型（2026-10-26 拍板派生制）：新结构 {level, basis:{field, excerpt}, confirmed}——
// level 由服务端按表单素材派生（B1/B3 用户亲口表述→业务；C 区三件套齐→用户；其余→功能），
// confirmed 为人工定稿（最高优先）；旧票数字段（business/user/function/evidence）仅存量数据兼容读取
export type RecognitionLevel = 'business' | 'user' | 'function'
export interface TypeRecognition {
  level?: RecognitionLevel; basis?: { field?: string; excerpt?: string }; confirmed?: string | null
  business?: number; user?: number; function?: number; evidence?: Record<string, string>
}
/** 生效判型层级：人工定稿优先；新结构 level 直读；旧票数结构折算（business/user≥0.7 对应层级，有票即功能兜底） */
export function recognitionLevelOf(recognition: TypeRecognition | null | undefined): RecognitionLevel | null {
  if (!recognition) return null
  const confirmed = recognition.confirmed
  if (confirmed === 'business' || confirmed === 'user' || confirmed === 'function') return confirmed
  if (confirmed != null) return null
  if (recognition.level) return recognition.level
  if ((recognition.business ?? 0) >= 0.7) return 'business'
  if ((recognition.user ?? 0) >= 0.7) return 'user'
  if (recognition.business || recognition.user || recognition.function) return 'function'
  return null
}
// 微需求快速通道（方案②）：AI 轻重判定，light 时表单卡显示「轻量提报 X/4」、红星只标最小集
export interface DemandMode { level: 'light' | 'standard'; evidence?: string }
export function demandModeOf(form: DemandForm): 'light' | 'standard' {
  const mode = form.ext?.mode as DemandMode | undefined
  return mode?.level === 'light' ? 'light' : 'standard'
}
export type DemandStatus =
  'DRAFT' | 'SUBMITTED' | 'NEED_INFO' | 'TRIAGE' | 'ANALYZING' | 'SOLUTION_REVIEW' |
  'CONFIRMED' | 'IN_PROGRESS' | 'ACCEPTANCE' | 'DONE' | 'CLOSED'
export interface DemandEntity extends DemandForm {
  id: number; demandNo: string | null; subtypeCode: string | null; revision: number
  status: DemandStatus
  submitterId: number; submitterName: string | null; submitterDept: string | null; channel: string; sessionId: number | null
  submittedAt: string | null; closedAt: string | null; closeReason: string | null; createdAt: string; updatedAt: string; quality: ElementStatus[]
  changeLogs: ChangeLog[]
  // P2 流转字段：老数据（4 态口径）可能缺省，前端全部按可选处理
  assigneeId?: number | null; assigneeName?: string | null
  onHold?: boolean; holdReason?: string | null
  confirmedAt?: string | null; doneAt?: string | null
  qualityScore?: number | null; satisfactionScore?: number | null
}
// 打回待补充（方案③）：管理员打回原因存 ext.returnReason，重提成功后由服务端清除
export interface ReturnReason { reason: string; returnedBy?: string; returnedAt?: string }
export function returnReasonOf(form: DemandForm): ReturnReason | null {
  const value = form.ext?.returnReason as ReturnReason | undefined
  return value && typeof value.reason === 'string' && value.reason ? value : null
}
export interface AgentMessage { id: number; sessionId: number; role: 'USER' | 'ASSISTANT' | 'SYSTEM'; content: string; structuredPayload: string | null; requestId?: string; createdAt: string }
// 手工改要素播报（FR-06）：ASSISTANT 消息的 structuredPayload 为此时前端渲染改动手卡片
export interface ManualChangePayload { kind: 'manualChange'; changes: { action: 'update' | 'fill' | 'clear'; label: string; old: string; new: string }[] }
export function parseManualChange(raw: string | null | undefined): ManualChangePayload | null {
  if (!raw) return null
  try {
    const payload = JSON.parse(raw) as ManualChangePayload | null
    return payload && payload.kind === 'manualChange' && Array.isArray(payload.changes) ? payload : null
  } catch { return null }
}
// 附件消息（阶段一）：USER 上传动作 + AI 固定回执，不参与质量快照回放
// purpose（2026-10-22 拍板）：parse=「让 AI 读懂图片」入口上传，识别成功后后端回写 parsed=true（「AI 已读取」标签）
export interface AttachmentPayload { kind: 'attachment' | 'attachmentReceipt'; attachmentId: number; fileName: string; fileKind?: 'IMAGE' | 'DOC'; size?: number; purpose?: 'archive' | 'parse'; parsed?: boolean }
export function parseAttachmentPayload(raw: string | null | undefined): AttachmentPayload | null {
  if (!raw) return null
  try {
    const payload = JSON.parse(raw) as AttachmentPayload | null
    return payload && (payload.kind === 'attachment' || payload.kind === 'attachmentReceipt') && payload.attachmentId ? payload : null
  } catch { return null }
}
// 打回播报（方案③）：管理员打回注入会话的白话通知，聊天流按普通 AI 消息渲染，不参与质量快照回放
export interface ReturnNoticePayload { kind: 'returnNotice'; reason: string }
export function parseReturnNotice(raw: string | null | undefined): ReturnNoticePayload | null {
  if (!raw) return null
  try {
    const payload = JSON.parse(raw) as ReturnNoticePayload | null
    return payload && payload.kind === 'returnNotice' && payload.reason ? payload : null
  } catch { return null }
}
// 口径改判播报（方案④）：提报人轻量↔常规改判注入会话的白话通知，渲染同 returnNotice，不参与质量快照回放
export interface ModeChangePayload { kind: 'modeChange'; from: 'light' | 'standard'; to: 'light' | 'standard' }
export function parseModeChange(raw: string | null | undefined): ModeChangePayload | null {
  if (!raw) return null
  try {
    const payload = JSON.parse(raw) as ModeChangePayload | null
    return payload && payload.kind === 'modeChange' && (payload.to === 'light' || payload.to === 'standard') ? payload : null
  } catch { return null }
}
// 归类改判播报（2026-10-20）：提报人确认/恢复判型注入会话的白话通知，渲染同 returnNotice，不参与质量快照回放
export interface TypeChangePayload { kind: 'typeChange' }
export function parseTypeChange(raw: string | null | undefined): TypeChangePayload | null {
  if (!raw) return null
  try {
    const payload = JSON.parse(raw) as TypeChangePayload | null
    return payload && payload.kind === 'typeChange' ? payload : null
  } catch { return null }
}
/** 会话质量快照回放只认真正的对话结果消息：手改播报/附件回执/打回播报/口径改判播报/归类改判播报都不算（与服务端 guide.py 同口径）。 */
export function isReplayablePayload(raw: string | null | undefined): boolean {
  return !!raw && !parseManualChange(raw) && !parseAttachmentPayload(raw) && !parseReturnNotice(raw) && !parseModeChange(raw) && !parseTypeChange(raw)
}
export interface DemandAttachment { id: number; demandId: number; fileName: string; kind: 'IMAGE' | 'DOC'; kindLabel: string; size: number; purpose?: 'archive' | 'parse'; parseStatus?: 'PARSED' | 'NO_TEXT' | 'FAILED' | null; createdAt: string }
export const listAttachments = (demandId: number): Promise<DemandAttachment[]> => get(`/demand/${demandId}/attachments`)
// purpose=parse（2026-10-22 拍板）：「让 AI 读懂图片」——后端同步调视觉模型转写（最长约 30s），
// 识别失败/无字自动降级为普通附件；timeout 放宽到 90s 覆盖解析等待
export function uploadAttachment(demandId: number, file: File, purpose: 'archive' | 'parse' = 'archive'): Promise<DemandAttachment> {
  const form = new FormData()
  form.append('file', file)
  const query = purpose === 'parse' ? '?purpose=parse' : ''
  return post(`/demand/${demandId}/attachments${query}`, form, { timeout: 90000 })
}
export const deleteAttachment = (demandId: number, attachmentId: number): Promise<unknown> => del(`/demand/${demandId}/attachments/${attachmentId}`)
/** 图片缩略图：鉴权拉 blob 转 objectURL（组件卸载时须 revokeObjectURL）。 */
export async function fetchAttachmentThumb(demandId: number, attachmentId: number): Promise<string> {
  const blob = await fetchBlob(`/demand/${demandId}/attachments/${attachmentId}/download`)
  return URL.createObjectURL(blob)
}
export const downloadAttachment = (demandId: number, attachmentId: number, fileName: string): Promise<void> =>
  downloadFile(`/demand/${demandId}/attachments/${attachmentId}/download`, fileName)
export const ATTACHMENT_SIZE_LIMIT = 10 * 1024 * 1024
export const ATTACHMENT_COUNT_LIMIT = 5
// 图片入口放宽为 image/*（2026-10-20 拍板）：手机拍照/相册文件名与格式不可靠（无扩展名、HEIC），
// 先保证各机型相机都能调起，格式把关交给「前端归一化（HEIC 转 JPG/补扩展名）+ 后端魔数兜底」
export const ATTACHMENT_ACCEPT = { image: 'image/*', doc: '.md,.pdf,.doc,.docx,.ppt,.pptx' }
export function fmtSize(size: number): string {
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)}MB`
  return `${Math.max(Math.round(size / 1024), 1)}KB`
}
export interface DemandDetail { demand: DemandEntity; quality: ElementStatus[]; standard: Standard | null; messages: AgentMessage[]; attachments?: DemandAttachment[] }
export interface PageResult<T> { records: T[]; total: number; size: number; current: number; pages: number }
export interface DemandQuery { page: number; size: number; status?: string }
export interface AdminQuery extends DemandQuery { type?: string; from?: string; to?: string }
export const getStandards = (): Promise<StandardSummary[]> => get('/standards')
export const getStandard = (type: string): Promise<Standard> => get(`/standards/${type}`)
export const createDraft = (data: DemandForm & { clientRequestId: string }): Promise<DemandEntity> => post('/demand', data)
export const updateDraft = (id: number, data: DemandForm & { expectedRevision: number; notifyChanges?: boolean }): Promise<DemandEntity> => put(`/demand/${id}`, data)
export const submitDemand = (id: number, expectedRevision: number): Promise<DemandEntity> => post(`/demand/${id}/submit`, { expectedRevision })
export const closeDemand = (id: number, reason: string): Promise<DemandEntity> => post(`/demand/${id}/close`, { reason })
// 提报口径改判（方案④）：轻量↔常规双向；2026-10-20 拍板打回补充期间不再锁口径，响应同 updateDraft 可直接刷新表单
export const changeDemandMode = (id: number, expectedRevision: number, level: 'light' | 'standard'): Promise<DemandEntity> =>
  post(`/demand/${id}/mode`, { expectedRevision, level })
export function nonEmptyQuery<T extends object>(query: T): Partial<T> {
  return Object.fromEntries(Object.entries(query).filter(([, value]) => value !== '' && value !== null && value !== undefined)) as Partial<T>
}
export const myDemands = (query: DemandQuery): Promise<PageResult<DemandEntity>> => get('/demand/my', nonEmptyQuery(query))
/** 「我的需求」tab 角标：待补充（NEED_INFO）需求数，与「待补充」筛选同口径，处理完自动消 */
export const myNeedInfoCount = (): Promise<{ count: number }> => get('/demand/my/need-info-count', undefined, { silent: true })
export const adminDemands = (query: AdminQuery): Promise<PageResult<DemandEntity>> => get('/admin/demand/list', nonEmptyQuery(query))
// 管理员打回待补充（方案③）：仅已提交需求可打回，原因必填，服务端写留痕并往会话注入播报
export const returnDemand = (id: number, reason: string): Promise<DemandEntity> => post(`/admin/demand/${id}/return`, { reason })
export const getDemand = (id: number): Promise<DemandDetail> => get(`/demand/${id}`)
// P2 状态时间线与验收：flow 接口返回流转留痕 + 当前用户可用操作（按钮显隐以它为准）
export interface TransitionLog {
  id: number; fromStatus: string | null; fromStatusLabel: string | null
  toStatus: string; toStatusLabel: string; event: string; eventLabel: string
  operatorName: string | null; holdFlag: boolean; comment: string | null; createdAt: string
}
export interface FlowDetail { transitions: TransitionLog[]; availableActions: { event: string; label: string }[] }
export const getFlow = (id: number): Promise<FlowDetail> => get(`/demand/${id}/flow`)
export const acceptanceReview = (id: number, data: {
  result: 'PASS' | 'REJECT'; qualityScore?: number; satisfactionScore?: number; opinion?: string
}): Promise<DemandEntity> => post(`/demand/${id}/acceptance-review`, data)
export const downloadMarkdown = (id: number, name: string): Promise<void> => downloadFile(`/demand/${id}/export.md`, `${name}.md`)
export const downloadXlsx = (query: Omit<AdminQuery, 'page' | 'size'>): Promise<void> => downloadFile('/admin/demand/export.xlsx', 'demandhub.xlsx', nonEmptyQuery(query) as Record<string, string>)
