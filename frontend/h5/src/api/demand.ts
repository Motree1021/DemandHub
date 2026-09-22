import { get, post, put, del } from './request'
import service from './request'

/** 分页结果（MyBatis-Plus Page 序列化结构） */
export interface PageResult<T> {
  records: T[]
  total: number
  size: number
  current: number
  pages: number
}

/** 需求主表实体 */
export interface DemandEntity {
  id: number
  demandNo: string
  title: string
  demandTypeCode: string
  subtypeCode: string | null
  content: string
  urgency: string
  status: string
  onHold: number
  holdReason: string | null
  holdSnapshotStatus: string | null
  submitterId: number
  actualDemanderId: number | null
  submitterOrgId: number | null
  submitterOrgSnapshot: string | null
  channel: string | null
  assigneeOrgId: number | null
  assigneeUserId: number | null
  projectId: number | null
  expectDeliveryAt: string | null
  actualDeliveryAt: string | null
  submittedAt: string | null
  closedAt: string | null
  closeReason: string | null
  qualityScore: number | null
  satisfactionScore: number | null
  createdAt: string
  updatedAt: string
  version: number
}

/** 列表行 VO */
export interface DemandListItem {
  id: number
  demandNo: string
  title: string
  demandTypeCode: string
  typeName: string | null
  subtypeCode: string | null
  urgency: string
  status: string
  onHold: number
  submitterId: number
  submitterName: string | null
  actualDemanderId: number | null
  submitterOrgId: number | null
  assigneeOrgId: number | null
  assigneeOrgName: string | null
  assigneeUserId: number | null
  assigneeUserName: string | null
  expectDeliveryAt: string | null
  submittedAt: string | null
  closedAt: string | null
  closeReason: string | null
  qualityScore: number | null
  satisfactionScore: number | null
  createdAt: string
}

/** 科技扩展 */
export interface ExtTech {
  relatedSystem?: string
  relatedModule?: string
  businessScenario?: string
  acceptanceCriteria?: string
}
/** 物料扩展 */
export interface ExtMaterial {
  materialSubtype?: string
  usageScenario?: string
  quantity?: number
  expectedArrivalAt?: string
}
/** 培训扩展 */
export interface ExtTraining {
  trainingSubtype?: string
  traineeObject?: string
  traineeCount?: number
  expectedCompleteAt?: string
}

export interface AttachmentItem {
  id: number
  bizType: string
  bizId: number
  fileName: string
  filePath: string
  fileSize: number
  mimeType: string
  ext: string
  uploadedBy: number
  createdAt: string
}

/** 需求详情 VO（后端拼装） */
export interface DemandDetail {
  demand: DemandEntity
  ext: ExtTech & ExtMaterial & ExtTraining | null
  typeName: string | null
  submitterName: string | null
  actualDemanderName: string | null
  assigneeOrgName: string | null
  assigneeUserName: string | null
  attachments: AttachmentItem[]
  availableActions: string[]
  holdDays: number | null
}

/** 流转日志 */
export interface TransitionLog {
  id: number
  demandId: number
  fromStatus: string | null
  toStatus: string
  action: string
  operatorId: number
  operatorSnapshot: string | null
  comment: string | null
  extra: string | null
  createdAt: string
}

export interface DemandPageQuery {
  current: number
  size: number
  status?: string
  demandTypeCode?: string
  urgency?: string
  keyword?: string
  onHold?: number
  mine?: boolean
  /** 提交时间排序：asc 升序 / desc 降序（默认） */
  submittedOrder?: 'asc' | 'desc'
}

/** 需求分页（数据权限由后端拦截器处理） */
export function pageDemands(q: DemandPageQuery): Promise<PageResult<DemandListItem>> {
  return get('/demand/demand/page', q)
}

/** 需求详情 */
export function getDemand(id: number): Promise<DemandDetail> {
  return get(`/demand/demand/${id}`)
}

/** 流转时间线 */
export function getTransitions(id: number): Promise<TransitionLog[]> {
  return get(`/demand/demand/${id}/transitions`)
}

export interface SubmitRequest {
  draftId?: number
  title: string
  demandTypeCode: string
  subtypeCode?: string
  content: string
  urgency: string
  expectDeliveryAt?: string
  actualDemanderId?: number
  /** 来源渠道由后端按会话 claims 落库，前端传值无效（P5 任务 5.5） */
  ext?: Record<string, unknown>
  attachmentIds?: number[]
}

export function submitDemand(data: SubmitRequest): Promise<DemandEntity> {
  return post('/demand/demand/submit', data)
}

export function withdrawDemand(id: number, reason: string): Promise<void> {
  return post(`/demand/demand/${id}/withdraw`, { reason })
}

export interface ResubmitRequest {
  title?: string
  content?: string
  urgency?: string
  expectDeliveryAt?: string
  ext?: Record<string, unknown>
  attachmentIds?: number[]
}

export function resubmitDemand(id: number, data: ResubmitRequest): Promise<DemandEntity> {
  return post(`/demand/demand/${id}/resubmit`, data)
}

export function startDemand(id: number): Promise<void> {
  return post(`/demand/demand/${id}/start`)
}

export function holdDemand(id: number, reason: string): Promise<void> {
  return post(`/demand/demand/${id}/hold`, { reason })
}

export function resumeDemand(id: number): Promise<void> {
  return post(`/demand/demand/${id}/resume`)
}

export function submitAcceptance(id: number): Promise<void> {
  return post(`/demand/demand/${id}/submit-acceptance`)
}

export interface AcceptanceReviewRequest {
  conclusion: 'PASS' | 'REJECT'
  qualityScore?: number
  satisfactionScore?: number
  comment?: string
}

export function acceptanceReview(id: number, data: AcceptanceReviewRequest): Promise<void> {
  return post(`/demand/demand/${id}/acceptance-review`, data)
}

/* ---------------- 草稿 ---------------- */

export interface DraftItem {
  id: number
  userId: number
  channel: string | null
  formPayload: string
  convertedDemandId: number | null
  createdAt: string
  updatedAt: string
}

export function saveDraft(data: { id?: number; formPayload: string }): Promise<DraftItem> {
  return post('/demand/draft/save', data)
}

export function listDrafts(): Promise<DraftItem[]> {
  return get('/demand/draft/list')
}

export function deleteDraft(id: number): Promise<void> {
  return del(`/demand/draft/${id}`)
}

/* ---------------- 受理 / 分派 ---------------- */

export interface TriageQueueQuery {
  current: number
  size: number
  urgency?: string
  demandTypeCode?: string
}

/** 待受理队列（本组织 SUBMITTED，经理） */
export function triageQueue(q: TriageQueueQuery): Promise<PageResult<DemandEntity>> {
  return get('/demand/triage/queue', q)
}

export function acceptDemand(id: number, comment?: string): Promise<void> {
  return post(`/demand/triage/${id}/accept`, comment ? { comment } : {})
}

export function returnDemand(id: number, comment: string): Promise<void> {
  return post(`/demand/triage/${id}/return`, { comment })
}

export function closeDemand(id: number, reason: string, duplicateOfId?: number): Promise<void> {
  return post(`/demand/triage/${id}/close`, { reason, duplicateOfId })
}

export function assignDemand(id: number, assigneeId: number, comment?: string): Promise<void> {
  return post(`/demand/triage/${id}/assign`, { assigneeId, comment })
}

export function claimDemand(id: number): Promise<void> {
  return post(`/demand/triage/${id}/claim`)
}

/* ---------------- 评论 ---------------- */

export interface CommentItem {
  id: number
  demandId: number
  authorId: number
  content: string
  mentionedUserIds: string | null
  createdAt: string
}

export function addComment(data: { demandId: number; content: string; mentionedUserIds?: number[]; attachmentIds?: number[] }): Promise<CommentItem> {
  return post('/demand/comment', data)
}

export function listComments(demandId: number): Promise<CommentItem[]> {
  return get('/demand/comment/list', { demandId })
}

/* ---------------- 附件（后端流式上传下载） ---------------- */

/** 上传附件：multipart 直传后端，返回附件元信息 */
export function uploadAttachment(bizType: string, bizId: number, file: File, onProgress?: (percent: number) => void): Promise<AttachmentItem> {
  const fd = new FormData()
  fd.append('bizType', bizType)
  fd.append('bizId', String(bizId))
  fd.append('file', file)
  return service.post('/demand/attachment/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded * 100) / e.total))
      }
    }
  }) as unknown as Promise<AttachmentItem>
}

export function listAttachments(bizType: string, bizId: number): Promise<AttachmentItem[]> {
  return get('/demand/attachment/list', { bizType, bizId })
}

export function deleteAttachment(id: number): Promise<void> {
  return del(`/demand/attachment/${id}`)
}

/** 图片预览：拉 blob 转 objectURL（下载接口需 token 鉴权，不能直接 <img src>） */
export async function previewAttachmentUrl(id: number): Promise<string> {
  const resp = await service.get(`/demand/attachment/${id}/download`, { responseType: 'blob' })
  return window.URL.createObjectURL(resp.data as Blob)
}

/* ---------------- 字典下拉 ---------------- */

export interface DictItem {
  id: number
  dictType: string
  itemCode: string
  itemName: string
  sort: number
  status: string
}

export function listDictItems(dictType: string): Promise<DictItem[]> {
  return get('/demand/dicts', { dictType })
}
