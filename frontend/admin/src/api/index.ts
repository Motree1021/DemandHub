import { del, get, patch, post, put } from './request'

/** P4 五角色：管理员/管理者（改型）/经理（受理族）/处理人/提报人（渠道默认，最小权限） */
export type RoleCode = 'ADMIN' | 'EXECUTIVE' | 'MANAGER' | 'HANDLER' | 'REPORTER'

/** 需求类型权限（2026-10-16 拍板，按人统一配）：仅业务角色（管理者/经理/处理人）需要配；
 * 管理员/提报人不受限；空 = 无权限（看不到也操作不了该类型需求） */
export type TypeCode = 'TECH' | 'MATL' | 'TRAIN'

export interface LoginUser {
  id: number
  name: string
  role: RoleCode
  roles: RoleCode[]
  isAdmin: boolean
  mustChangePwd: boolean
}
export interface LoginResult {
  accessToken: string
  refreshToken: string
  expiresIn: number
  mustChangePwd: boolean
  user: LoginUser
}

export const authApi = {
  login: (loginAccount: string, password: string) =>
    post<LoginResult>('/auth/login', { loginAccount, password }),
  changePassword: (oldPassword: string, newPassword: string) =>
    post<{ success: boolean }>('/auth/change-password', { oldPassword, newPassword }),
  logout: (refreshToken: string) =>
    post<{ success: boolean }>('/auth/logout', { refreshToken }),
  me: () => get<LoginUser>('/auth/me'),
}

export interface UserRow {
  id: number
  loginAccount: string | null
  name: string
  wecomUserid: string
  role: RoleCode
  roles: RoleCode[]
  typeScope: TypeCode[] | null
  status: 'ACTIVE' | 'DISABLED'
  channel: string
  phone: string | null
  email: string | null
  mustChangePwd: boolean
  lastLoginAt: string | null
  createdAt: string
  /** OneID 一期：已挂接的渠道身份（仅列表出参带；空=未挂接） */
  channelIdentities: ChannelIdentityBrief[] | null
}
export interface UserListResult { list: UserRow[]; total: number; page: number; size: number }

/** OneID 一期：渠道身份（一把渠道钥匙）。channelUserName 为渠道侧姓名快照 */
export interface ChannelIdentityBrief { channel: string; channelUserId: string; channelUserName: string }
export interface ChannelIdentityRow extends ChannelIdentityBrief {
  id: number
  /** 归属人：待归一=渠道临时人；已归一=PC 用户（OneID 用户） */
  ownerId: number
  ownerName: string
  ownerAccount: string | null
  /** 最近活跃（待归一排序键）；已归一列表按挂接/改挂时间倒序 */
  lastSeenAt: string | null
  /** 同名线索（仅待归一附带）：姓名完全一致的 ACTIVE 正式用户，至多3个——同名≠同一人，仅供核对 */
  suspects?: { id: number; name: string; loginAccount: string | null }[]
}
export interface UserIdentity extends ChannelIdentityBrief { id: number; createdAt: string | null }
export interface LinkResult {
  identityId: number
  channel: string
  channelUserId: string
  sourceUser: { id: number; name: string }
  targetUser: { id: number; name: string }
  movedCounts: Record<string, number>
}
export interface IdentityLinkLogRow {
  id: number
  action: 'LINK' | 'REBIND'
  channel: string
  channelUserId: string
  fromUserId: number
  fromUserName: string
  toUserId: number
  toUserName: string
  /** 过户明细（改挂不搬数据为 null） */
  movedCounts: Record<string, number> | null
  operatorName: string
  createdAt: string | null
}

export const identitiesApi = {
  /** 渠道身份列表：linked=false 待归一（归属人仍是临时人，附同名线索），linked=true 已归一 */
  list: (params: { linked: boolean; keyword?: string; page?: number; size?: number }) =>
    get<{ list: ChannelIdentityRow[]; total: number }>('/admin/channel-identities', params),
  /** 挂接/改挂审计记录（「挂接记录」Tab） */
  linkLogs: (params: { page?: number; size?: number }) =>
    get<{ list: IdentityLinkLogRow[]; total: number }>('/admin/identity-link-logs', params),
  /** 某 PC 用户已挂接的渠道身份 */
  ofUser: (userId: number) => get<UserIdentity[]>(`/admin/users/${userId}/channel-identities`),
  /** 挂接：身份改指 PC 用户 + 临时人数据全量过户 + 停用；返回过户数据量供确认 */
  link: (userId: number, identityId: number) =>
    post<LinkResult>(`/admin/users/${userId}/channel-identities`, { identityId }),
  /** 改挂：已归属身份 A→B，只移钥匙不搬历史数据 */
  rebind: (identityId: number, userId: number) =>
    post<Omit<LinkResult, 'movedCounts'>>(`/admin/channel-identities/${identityId}/rebind`, { userId }),
}

export const usersApi = {
  list: (params: { page: number; size: number; keyword?: string; role?: string; status?: string; channel?: string }) =>
    get<UserListResult>('/admin/users', params),
  create: (data: { loginAccount: string; name: string; phone: string; email?: string; initialPassword: string; role?: RoleCode; roles?: RoleCode[]; types?: TypeCode[] }) =>
    post<UserRow>('/admin/users', data),
  updateRoles: (id: number, roles: RoleCode[], types?: TypeCode[]) =>
    put<UserRow>(`/admin/users/${id}/roles`, { roles, types }),
  activate: (id: number) => put<UserRow>(`/admin/users/${id}/activate`),
  disable: (id: number) => put<UserRow>(`/admin/users/${id}/disable`),
  resetPassword: (id: number, newPassword: string) =>
    post<{ success: boolean }>(`/admin/users/${id}/reset-password`, { newPassword }),
}

// ---- P2 状态机与全流程流转 ----

export interface DemandRow {
  id: number
  demandNo: string | null
  title: string | null
  demandTypeCode: string | null
  subtypeCode: string | null
  content?: string | null
  urgency: 'NORMAL' | 'URGENT' | 'CRITICAL' | null
  status: string
  submitterId: number
  submitterName: string | null
  submitterDept?: string | null
  assigneeId: number | null
  assigneeName: string | null
  onHold: boolean
  holdReason: string | null
  expectDeliveryAt: string | null
  submittedAt: string | null
  confirmedAt: string | null
  doneAt: string | null
  closedAt?: string | null
  closeReason?: string | null
  qualityScore: number | null
  satisfactionScore: number | null
  splitFromId?: number | null
  revision: number
  createdAt: string
  updatedAt: string
  ext?: Record<string, unknown>
  elements?: Record<string, Record<string, unknown>>
}
export interface PageResult<T> { records: T[]; total: number; size: number; current: number; pages: number }
export interface AssigneeOption { id: number; name: string; role: string; department: string | null }

export const triageApi = {
  queue: (params: { page: number; size: number; urgency?: string; typeCode?: string }) =>
    get<PageResult<DemandRow>>('/triage/queue', params),
  pool: (params: { page: number; size: number; urgency?: string }) =>
    get<PageResult<DemandRow>>('/triage/pool', params),
  counts: () => get<{ queue: number; pool: number }>('/triage/counts'),
  mine: (params: { page: number; size: number; status?: string }) =>
    get<PageResult<DemandRow>>('/triage/mine', params),
  demands: (params: { page: number; size: number; status?: string; urgency?: string; typeCode?: string; includeDrafts?: boolean }) =>
    get<PageResult<DemandRow>>('/triage/demands', params),
  // 分派候选人按需求类型过滤（类型权限管控点）：仅返回覆盖该类型的处理人，ADMIN 直通
  assignees: (typeCode: string) => get<AssigneeOption[]>('/triage/assignees', { typeCode }),
  accept: (id: number, comment?: string) => post<DemandRow>(`/triage/${id}/accept`, { comment }),
  returnDemand: (id: number, reason: string) => post<DemandRow>(`/triage/${id}/return`, { reason }),
  close: (id: number, reason: string, duplicateOfId?: number) =>
    post<DemandRow>(`/triage/${id}/close`, { reason, duplicateOfId }),
  assign: (id: number, assigneeId: number, comment?: string) =>
    post<DemandRow>(`/triage/${id}/assign`, { assigneeId, comment }),
  claim: (id: number) => post<DemandRow>(`/triage/${id}/claim`),
  returnPool: (id: number, reason: string) => post<DemandRow>(`/triage/${id}/return-pool`, { reason }),
  changeType: (id: number, newTypeCode: string, comment?: string) =>
    post<DemandRow>(`/triage/${id}/change-type`, { newTypeCode, comment }),
}

export interface TransitionLog {
  id: number
  fromStatus: string | null
  fromStatusLabel: string | null
  toStatus: string
  toStatusLabel: string
  event: string
  eventLabel: string
  operatorName: string | null
  holdFlag: boolean
  comment: string | null
  createdAt: string
}
export interface FlowDetail {
  transitions: TransitionLog[]
  availableActions: { event: string; label: string }[]
}

export const flowApi = {
  detail: (demandId: number) => get<FlowDetail>(`/demand/${demandId}/flow`),
  start: (id: number) => post<DemandRow>(`/demand/${id}/start`),
  hold: (id: number, reason: string) => post<DemandRow>(`/demand/${id}/hold`, { reason }),
  resume: (id: number) => post<DemandRow>(`/demand/${id}/resume`),
  submitAcceptance: (id: number) => post<DemandRow>(`/demand/${id}/submit-acceptance`),
  acceptanceReview: (id: number, data: {
    result: 'PASS' | 'REJECT'; qualityScore?: number; satisfactionScore?: number; opinion?: string
  }) => post<DemandRow>(`/demand/${id}/acceptance-review`, data),
  split: (id: number, items: { title: string; summary?: string }[]) =>
    post<DemandRow[]>(`/demand/${id}/split`, { items }),
}

export const demandApi = {
  // GET /demand/{id} 返回包装体 {demand, quality, standard, messages, attachments}（与 H5 提报端同结构）
  detail: (id: number) => get<DemandDetailBundle>(`/demand/${id}`),
  close: (id: number, reason: string) => post<DemandRow>(`/demand/${id}/close`, { reason }),
  // 删除草稿需求（2026-10-22 拍板）：仅 ADMIN、仅 DRAFT 态，物理删除不可恢复
  remove: (id: number) => del<void>(`/demand/${id}`),
  // 管理端改要素（详情页双击编辑）：乐观锁 expectedRevision；返回最新 demand + 重算后的 quality
  updateElements: (id: number, data: { expectedRevision: number; elements: Record<string, Record<string, unknown>> }) =>
    patch<{ demand: DemandRow; quality: ElementStatus[] }>(`/demand/${id}/elements`, data),
}

// ---- 需求详情包装体（H5 同款）：需求本体 + AI 质检 + 要素标准 + 对话记录 + 附件清单 ----
export interface StandardField {
  key: string
  label: string
  path?: string | null
  kind: 'text' | 'enum' | 'number' | 'date' | 'list'
  zone?: 'A' | 'B' | 'C' | 'D' | null
  options?: Record<string, string>
}
export interface StandardDef {
  type: string
  name: string
  version: string
  elements: StandardField[]
  commonFields: StandardField[]
  optionalFields: StandardField[]
  subtypeFields: Record<string, StandardField[]>
}
export interface MessageRow {
  id: number
  role: 'USER' | 'ASSISTANT' | 'SYSTEM'
  content: string
  structuredPayload: string | null
  createdAt: string
}
export interface AttachmentRow { id: number; fileName: string; kind: 'IMAGE' | 'DOC'; kindLabel: string; size: number }
export interface ElementStatus { key: string; label?: string; status: 'OK' | 'VAGUE' | 'MISSING' | 'SKIP'; note: string }
export interface DemandDetailBundle {
  demand: DemandRow
  quality: ElementStatus[]
  standard: StandardDef | null
  messages: MessageRow[]
  attachments: AttachmentRow[]
}

export interface SolutionRow {
  id: number
  demandId: number
  version: number
  authorId: number
  authorName: string | null
  specContent: string | null
  solutionContent: string | null
  planDeliveryAt: string | null
  status: 'DRAFT' | 'SUBMITTED' | 'APPROVED' | 'REJECTED'
  remark: string | null
  createdAt: string
  updatedAt: string
}
export interface ReviewRow {
  id: number
  demandId: number
  reviewType: 'SOLUTION' | 'ACCEPTANCE'
  targetId: number | null
  result: 'PASS' | 'REJECT'
  opinion: string | null
  qualityScore: number | null
  satisfactionScore: number | null
  reviewerName: string | null
  createdAt: string
}

export const solutionApi = {
  list: (demandId: number) => get<SolutionRow[]>('/solution/list', { demandId }),
  create: (data: {
    demandId: number; specContent?: string; solutionContent?: string; planDeliveryAt?: string; remark?: string
  }) => post<SolutionRow>('/solution', data),
  update: (id: number, data: {
    specContent?: string; solutionContent?: string; planDeliveryAt?: string; remark?: string
  }) => put<SolutionRow>(`/solution/${id}`, data),
  submitReview: (id: number) => post<SolutionRow>(`/solution/${id}/submit-review`),
  review: (id: number, result: 'PASS' | 'REJECT', opinion?: string) =>
    post<SolutionRow>(`/solution/${id}/review`, { result, opinion }),
  compare: (demandId: number, v1: number, v2: number) =>
    get<{ items: SolutionRow[] }>('/solution/compare', { demandId, v1, v2 }),
  reviews: (demandId: number, reviewType?: string) =>
    get<ReviewRow[]>('/solution/reviews', { demandId, reviewType }),
}

export interface CommentRow {
  id: number
  demandId: number
  authorId: number
  authorName: string | null
  content: string
  createdAt: string
  updatedAt: string
}

export const commentApi = {
  list: (demandId: number) => get<CommentRow[]>('/comment/list', { demandId }),
  add: (demandId: number, content: string) => post<CommentRow>('/comment', { demandId, content }),
  update: (id: number, content: string) => put<CommentRow>(`/comment/${id}`, { content }),
}

export interface EffortRow {
  id: number
  demandId: number
  userId: number
  userName: string | null
  hours: number
  workDate: string
  remark: string | null
  createdAt: string
}
export interface EffortSummary {
  totalHours: number
  byUser: { userId: number; userName: string; hours: number }[]
  byDate: { workDate: string; hours: number }[]
}

export const effortApi = {
  list: (demandId: number) => get<EffortRow[]>('/effort/list', { demandId }),
  summary: (demandId: number) => get<EffortSummary>('/effort/summary', { demandId }),
  add: (data: { demandId: number; workDate: string; hours: number; remark?: string }) =>
    post<EffortRow>('/effort', data),
  update: (id: number, data: { workDate: string; hours: number; remark?: string }) =>
    put<EffortRow>(`/effort/${id}`, data),
}

export interface RelationRow {
  id: number
  type: 'PARENT' | 'DEPENDS' | 'DUPLICATE' | 'SPLIT'
  direction: 'OUT' | 'IN'
  otherDemandId: number
  otherDemandNo: string | null
  otherTitle: string | null
  otherStatus: string | null
  createdAt: string
}

export const relationApi = {
  list: (demandId: number) => get<RelationRow[]>('/relation/list', { demandId }),
  add: (demandId: number, relatedDemandId: number, relationType: string) =>
    post<void>('/relation', { demandId, relatedDemandId, relationType }),
  remove: (id: number) => del<void>(`/relation/${id}`),
}

// ---- P3 处理辅助 Agent（AI 生成内容一律进草稿区，人工确认后才入库）+ RAG 相似需求 ----

export interface AgentSessionRow {
  id: number
  sessionNo: string
  userId: number
  scene: 'SUBMIT_GUIDE' | 'HANDLE_ASSIST'
  demandId: number
  title: string | null
  status: string
  createdAt: string
  updatedAt: string
}

/** QUESTIONS → string[]；SOLUTION → {specContent, solutionContent} */
export type AssistDraftContent = string[] | { specContent?: string; solutionContent?: string }
export interface AssistDraftRow {
  id: number
  demandId: number
  sessionId: number
  draftType: 'QUESTIONS' | 'SOLUTION'
  content: AssistDraftContent
  status: 'PENDING' | 'CONFIRMED' | 'DISCARDED'
  confirmedAt: string | null
  targetSolutionId: number | null
  createdAt: string
  updatedAt: string
}

export interface SimilarHit {
  demandId: number
  demandNo: string
  title: string
  demandTypeCode: string | null
  score: number
}

export const assistApi = {
  // HANDLE_ASSIST 会话为需求级共享工作区：重复调用返回同一会话
  openSession: (demandId: number) =>
    post<AgentSessionRow>('/agent/session', { demandId, scene: 'HANDLE_ASSIST' }),
  generateQuestions: (sessionId: number) =>
    post<AssistDraftRow>('/agent/assist/questions', { sessionId }),
  generateSolution: (sessionId: number) =>
    post<AssistDraftRow>('/agent/assist/solution', { sessionId }),
  drafts: (demandId: number) => get<AssistDraftRow[]>('/agent/assist/drafts', { demandId }),
  confirm: (draftId: number, data: { specContent?: string; solutionContent?: string; planDeliveryAt?: string }) =>
    post<AssistDraftRow>(`/agent/assist/drafts/${draftId}/confirm`, data),
  discard: (draftId: number) => post<{ success: boolean }>(`/agent/assist/drafts/${draftId}/discard`),
}

export const ragApi = {
  similar: (demandId: number, topN = 5) => get<SimilarHit[]>('/agent/rag/similar', { demandId, topN }),
}

// ---- P4 通知中心 ----

export interface NotificationRow {
  id: number
  demandId: number | null
  templateCode: string | null
  notifyType: string | null
  title: string
  content: string | null
  link: string | null
  isRead: boolean
  readAt: string | null
  createdAt: string
}
export interface PreferenceRow { notifyType: string; enabled: boolean; closable: boolean }

export const notificationApi = {
  mine: (params: { current: number; size: number; isRead?: boolean }) =>
    get<PageResult<NotificationRow>>('/notification/mine', params),
  unreadCount: () => get<{ count: number }>('/notification/mine/unread-count'),
  read: (id: number) => put<{ updated: number }>(`/notification/${id}/read`),
  readAll: () => put<{ updated: number }>('/notification/mine/read-all'),
  preferences: () => get<PreferenceRow[]>('/notification/preferences'),
  savePreference: (notifyType: string, enabled: boolean) =>
    put<{ success: boolean }>('/notification/preferences', { notifyType, enabled }),
}

// ---- P4 统计看板（一期 DataScope=全量） ----

export type BoardRange = 'week' | 'month' | 'quarter' | 'custom'
export interface BoardQuery { range: BoardRange; from?: string; to?: string }
export interface ManagerBoard {
  kpi: { monthNew: number; inflight: number; done: number; slaOver: number; avgCycleHours: number | null }
  trend: { weekStart: string; newCnt: number; doneCnt: number }[]
  typeDistribution: { typeCode: string; cnt: number }[]
  channelDistribution: { channel: string; cnt: number }[]
  deptBacklog: { dept: string; cnt: number }[]
  slaHealth: { normal: number; warn: number; over: number }
}
export interface OrgBoard {
  pendingAccept: number
  pool: number
  processing: number
  weekDone: number
  avgInflightPerHandler: number
  memberWorkload: { userId: number; userName: string; inflightCnt: number; effortHours: number }[]
}

export const dashboardApi = {
  manager: (params: BoardQuery) => get<ManagerBoard>('/dashboard/manager', params),
  org: (params: BoardQuery) => get<OrgBoard>('/dashboard/org', params),
  statRefresh: () => post<{ rows: number }>('/dashboard/stat-refresh'),
}

// ---- P4 报表导出 ----

export interface ReportTaskRow {
  id: number
  taskNo: string
  reportType: string
  status: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED'
  fileName: string | null
  errorMsg: string | null
  createdAt: string
  finishedAt: string | null
}
export interface ReportExportParams {
  status?: string; demandTypeCode?: string; urgency?: string; keyword?: string
  submittedFrom?: string; submittedTo?: string; mine?: boolean
}

export const reportApi = {
  export: (params: ReportExportParams) =>
    post<{ id: number; taskNo: string }>('/report/export', { reportType: 'DEMAND_LIST', params }),
  tasks: (params: { current: number; size: number }) =>
    get<PageResult<ReportTaskRow>>('/report/tasks', params),
  downloadPath: (taskId: number) => `/report/download/${taskId}`,
}

// ---- P4 通知模板管理（仅 ADMIN） ----

export interface NotifyTemplateRow {
  id: number
  templateCode: string
  templateName: string
  titleTemplate: string
  contentTemplate: string
  status: 'ACTIVE' | 'INACTIVE'
  remark: string | null
  createdAt: string
  updatedAt: string
}

export const notifyTemplateApi = {
  list: () => get<NotifyTemplateRow[]>('/admin/notification-templates'),
  create: (data: { templateCode: string; templateName: string; titleTemplate: string; contentTemplate: string; remark?: string }) =>
    post<NotifyTemplateRow>('/admin/notification-templates', data),
  update: (id: number, data: Partial<{ templateName: string; titleTemplate: string; contentTemplate: string; status: string; remark: string }>) =>
    put<NotifyTemplateRow>(`/admin/notification-templates/${id}`, data),
  remove: (id: number) => del<{ success: boolean }>(`/admin/notification-templates/${id}`),
  preview: (data: { templateCode?: string; titleTemplate?: string; contentTemplate?: string; variables: Record<string, unknown> }) =>
    post<{ title: string; content: string }>('/admin/notification-templates/preview', data),
}

// ---- P5 业务字典（管理端仅 ADMIN；/dicts 登录用户查启用项） ----

export interface SysDictRow {
  id: number
  dictType: string
  itemCode: string
  itemName: string
  sort: number
  status: 'ACTIVE' | 'DISABLED'
  createdAt: string
  updatedAt: string
}

export const dictApi = {
  list: (dictType?: string) => get<SysDictRow[]>('/admin/dicts', dictType ? { dictType } : undefined),
  types: () => get<string[]>('/admin/dicts/types'),
  create: (data: { dictType: string; itemCode: string; itemName: string; sort?: number }) =>
    post<SysDictRow>('/admin/dicts', data),
  update: (id: number, data: Partial<{ itemName: string; sort: number; status: string }>) =>
    put<SysDictRow>(`/admin/dicts/${id}`, data),
  // 登录用户查启用项（表单下拉用）
  active: (dictType: string) => get<SysDictRow[]>('/dicts', { dictType }),
}

// ---- P5 需求类型管理（仅 ADMIN；五区标准仍走 yaml） ----

export interface DemandTypeRow {
  id: number
  typeCode: string
  typeName: string
  parentTypeCode: string | null
  defaultOrgId: number | null
  stateMachineKey: string
  slaConfig: unknown
  sort: number
  status: 'ACTIVE' | 'DISABLED'
  createdAt: string
  updatedAt: string
}

export const typeApi = {
  list: () => get<DemandTypeRow[]>('/admin/types'),
  create: (data: { typeCode: string; typeName: string; defaultOrgId?: number; stateMachineKey?: string; sort?: number }) =>
    post<DemandTypeRow>('/admin/types', data),
  update: (id: number, data: Partial<{ typeName: string; defaultOrgId: number; stateMachineKey: string; sort: number; status: string }>) =>
    put<DemandTypeRow>(`/admin/types/${id}`, data),
}

// ---- P5 状态机管理（仅 ADMIN；配置列表口径，规则集走 configJson 整包） ----

export interface StateMachineRow {
  id: number
  configKey: string
  configName: string
  configJson: string
  version: number
  status: 'ACTIVE' | 'DISABLED'
  remark: string | null
  createdAt: string
  updatedAt: string
}

export const stateMachineApi = {
  list: () => get<StateMachineRow[]>('/admin/state-machines'),
  defaultJson: () => get<{ configJson: string }>('/admin/state-machines/default-json'),
  create: (data: { configKey: string; configName: string; configJson: string; remark?: string }) =>
    post<StateMachineRow>('/admin/state-machines', data),
  update: (id: number, data: Partial<{ configName: string; configJson: string; status: string; remark: string }>) =>
    put<StateMachineRow>(`/admin/state-machines/${id}`, data),
  reload: () => post<{ rules: number }>('/admin/state-machines/reload'),
}

// ---- P5 SLA 配置管理（仅 ADMIN；类型 × 状态 组合的停留时长阈值） ----

export interface SlaConfigRow {
  id: number
  demandTypeCode: string
  status: string
  warnMinutes: number
  maxMinutes: number
  enabled: boolean
  remark: string | null
  createdAt: string
  updatedAt: string
}

export const slaApi = {
  list: (demandTypeCode?: string) =>
    get<SlaConfigRow[]>('/admin/sla-configs', demandTypeCode ? { demandTypeCode } : undefined),
  create: (data: { demandTypeCode: string; status: string; warnMinutes: number; maxMinutes: number; remark?: string }) =>
    post<SlaConfigRow>('/admin/sla-configs', data),
  update: (id: number, data: Partial<{ warnMinutes: number; maxMinutes: number; enabled: boolean; remark: string }>) =>
    put<SlaConfigRow>(`/admin/sla-configs/${id}`, data),
  remove: (id: number) => del(`/admin/sla-configs/${id}`),
}

// ---- P5 渠道管理（仅 ADMIN；只做登记/启停，无新增删除；secret 已脱敏） ----

export interface ChannelRow {
  id: number
  channelCode: string
  channelName: string
  appId: string | null
  callbackEnabled: boolean
  status: 'ACTIVE' | 'DISABLED'
  whitelistEnabled: boolean
  whitelistContact: string | null
  configJson: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
}

export interface DeptUnmappedRow {
  id: number
  channelCode: string
  deptId: string
  deptName: string | null
  deptPath: string | null
  sampleChannelUserId: string | null
  hitCount: number
  firstSeenAt: string
  lastSeenAt: string
}

export const channelApi = {
  list: () => get<ChannelRow[]>('/admin/channels'),
  updateStatus: (id: number, status: 'ACTIVE' | 'DISABLED') =>
    put<ChannelRow>(`/admin/channels/${id}/status`, { status }),
  unmapped: (channelCode?: string) =>
    get<DeptUnmappedRow[]>('/admin/channels/dept-unmapped', channelCode ? { channelCode } : undefined),
  removeUnmapped: (id: number) => del(`/admin/channels/dept-unmapped/${id}`),
}

// ---- 渠道白名单（仅 ADMIN；控制渠道用户能否进入 H5，全部操作后端落留痕） ----

export interface WhitelistEntry {
  id: number
  channelCode: string
  channelUserId: string
  displayName: string | null
  status: 'ENABLED' | 'DISABLED'
  lastLoginAt: string | null
  createdByName: string | null
  createdAt: string
  updatedAt: string
}

export interface WhitelistListResult {
  list: WhitelistEntry[]
  total: number
  page: number
  size: number
  stats: { enabled: number; disabled: number }
}

export interface WhitelistLogRow {
  id: number
  action: 'ADD' | 'ENABLE' | 'DISABLE' | 'REMOVE' | 'SWITCH_ON' | 'SWITCH_OFF' | 'UPDATE_CONTACT'
  channelCode: string
  channelUserId: string | null
  operatorName: string
  detail: string | null
  createdAt: string
}

export interface WhitelistPendingRow {
  userId: number
  wecomUserid: string
  name: string
  deptName: string | null
  lastLoginAt: string | null
  demandCount: number
}

export interface WhitelistBatchResult {
  added: number
  addedIds: string[]
  duplicated: string[]
  invalid: string[]
}

export const whitelistApi = {
  list: (channelCode: string, params: { page: number; size: number; keyword?: string; status?: string }) =>
    get<WhitelistListResult>(`/admin/channels/${channelCode}/whitelist`, params),
  add: (channelCode: string, data: { channelUserId: string; displayName?: string }) =>
    post<WhitelistEntry>(`/admin/channels/${channelCode}/whitelist`, data),
  addBatch: (channelCode: string, entries: { channelUserId: string; displayName?: string }[]) =>
    post<WhitelistBatchResult>(`/admin/channels/${channelCode}/whitelist/batch`, { entries }),
  updateStatus: (id: number, status: 'ENABLED' | 'DISABLED') =>
    put<WhitelistEntry>(`/admin/channels/whitelist/${id}/status`, { status }),
  remove: (id: number) => del(`/admin/channels/whitelist/${id}`),
  logs: (channelCode: string, params: { page: number; size: number }) =>
    get<{ list: WhitelistLogRow[]; total: number; page: number; size: number }>(
      `/admin/channels/${channelCode}/whitelist/logs`, params),
  pending: (channelCode: string) =>
    get<WhitelistPendingRow[]>(`/admin/channels/${channelCode}/whitelist/pending`),
  updateConfig: (channelCode: string, data: { whitelistEnabled?: boolean; whitelistContact?: string }) =>
    put<{ whitelistEnabled: boolean; whitelistContact: string | null }>(
      `/admin/channels/${channelCode}/whitelist/config`, data),
}

// ---- P5 组织管理（仅 ADMIN；物化路径树，移动=换父级） ----

export interface OrgNode {
  orgId: number
  name: string
  level: 'LINE' | 'DEPT' | 'GROUP'
  parentId: number
  path: string
  orgKind: 'REPORTER' | 'ASSIGNER' | 'BOTH' | null
  externalDeptId: string | null
  status?: 'ACTIVE' | 'DISABLED'
  children?: OrgNode[]
}

export const orgApi = {
  list: () => get<OrgNode[]>('/admin/orgs'),
  tree: () => get<OrgNode[]>('/admin/orgs/tree'),
  create: (data: { name: string; level: string; parentId: number; orgKind: string; externalDeptId?: string }) =>
    post<OrgNode>('/admin/orgs', data),
  update: (id: number, data: Partial<{ name: string; level: string; parentId: number; orgKind: string; externalDeptId: string | null; status: string }>) =>
    put<OrgNode>(`/admin/orgs/${id}`, data),
  remove: (id: number) => del(`/admin/orgs/${id}`),
}
