import { get, post, put, del } from './request'
import type { PageResult, UserSnapshotVO, OrgNode } from './grant'

/* ==================== 用户管理（/system/user，仅 ADMIN） ==================== */

/** 管理端用户（/system/user/page 返回完整 UserSnapshot） */
export interface AdminUser extends UserSnapshotVO {
  loginName?: string | null
  phone?: string | null
  email?: string | null
  employeeNo?: string | null
  wecomId?: string | null
  isEmployee?: number | null
  mergedToUserId?: number | null
  lastLoginChannel?: string | null
  lastLoginAt?: string | null
  createdAt?: string
}

/** 用户分页（完整快照） */
export function pageAdminUsers(params: { current: number; size: number; keyword?: string; status?: string }): Promise<PageResult<AdminUser>> {
  return get('/system/user/page', params)
}

/** 用户详情 */
export function getUserDetail(id: number): Promise<AdminUser> {
  return get(`/system/user/${id}`)
}

export interface CompleteUserRequest {
  name: string
  phone?: string | null
  email?: string | null
  employeeNo?: string | null
  primaryOrgId?: number | null
}

/** PENDING 用户补全激活 */
export function completeUser(id: number, data: CompleteUserRequest): Promise<void> {
  return post(`/system/user/${id}/complete`, data)
}

/** 激活用户 */
export function activateUser(id: number): Promise<void> {
  return post(`/system/user/${id}/activate`)
}

/** 停用用户 */
export function disableUser(id: number): Promise<void> {
  return post(`/system/user/${id}/disable`)
}

/** 合并预览：各清单待迁移行数 */
export function mergePreview(sourceUserId: number): Promise<Record<string, number>> {
  return get('/system/user/merge/preview', { sourceUserId })
}

/** 合并用户（不可恢复） */
export function mergeUsers(data: { sourceUserId: number; targetUserId: number }): Promise<void> {
  return post('/system/user/merge', data)
}

/** 渠道映射 */
export interface ChannelMapping {
  id: number
  channelCode: string
  channelUserId: string
  demandUserId: number
  channelName: string | null
  channelPhone: string | null
  channelDept: string | null
  matchType: string
  boundAt: string
}

export function userMappings(id: number): Promise<ChannelMapping[]> {
  return get(`/system/user/${id}/mappings`)
}

/** 设置登录账号 */
export function setLoginAccount(id: number, loginName: string): Promise<void> {
  return put(`/system/user/${id}/login-account`, { loginName })
}

/** 重置密码（重置后用户下次登录强制改密） */
export function resetPassword(id: number, newPassword: string): Promise<void> {
  return put(`/system/user/${id}/reset-password`, { newPassword })
}

/* ==================== 组织管理（/system/org，仅 ADMIN） ==================== */

/** 管理端组织节点（含渠道校准与状态字段） */
export interface AdminOrgNode extends OrgNode {
  externalDeptId?: string | null
  status?: string
  children?: AdminOrgNode[]
}

/** 组织树（管理端，含 externalDeptId/status） */
export function adminOrgTree(): Promise<AdminOrgNode[]> {
  return get('/system/org/tree')
}

export interface OrgSaveRequest {
  id?: number
  name: string
  level: 'LINE' | 'DEPT' | 'GROUP'
  parentId: number
  orgKind: 'REPORTER' | 'ASSIGNER' | 'BOTH'
  externalDeptId?: string | null
  status?: string | null
}

/** 新增组织，返回新 id */
export function createOrg(data: OrgSaveRequest): Promise<number> {
  return post('/system/org', data)
}

/** 更新组织 */
export function updateOrg(id: number, data: OrgSaveRequest): Promise<void> {
  return put(`/system/org/${id}`, data)
}

/** 删除组织（存在子组织/用户/授权/需求引用时将被拒绝） */
export function deleteOrg(id: number): Promise<void> {
  return del(`/system/org/${id}`)
}

/* ==================== 渠道管理（/system/channel，仅 ADMIN） ==================== */

export interface ChannelVO {
  id: number
  channelCode: string
  channelName: string
  appId: string
  callbackEnabled: boolean
  status: 'ACTIVE' | 'DISABLED'
  ssoVerifyBaseUrl: string | null
  appKey: string | null
  appSecret: string | null
  ticketTtlSeconds: number | null
  timeoutMs: number | null
  ssoConfigured: boolean
  updatedAt: string
}

export function listChannels(): Promise<ChannelVO[]> {
  return get('/system/channel/list')
}

/** 启停渠道 */
export function updateChannelStatus(id: number, status: 'ACTIVE' | 'DISABLED'): Promise<void> {
  return put(`/system/channel/${id}/status`, { status })
}

export interface ChannelConfigRequest {
  appId?: string
  ssoVerifyBaseUrl?: string
  appKey?: string
  appSecret?: string
  ticketTtlSeconds?: number
  timeoutMs?: number
}

/** 更新渠道 SSO 配置（appSecret 留空=不更换） */
export function updateChannelConfig(id: number, data: ChannelConfigRequest): Promise<void> {
  return put(`/system/channel/${id}/config`, data)
}

/** 连接测试，返回结果文案 */
export function testChannel(id: number): Promise<string> {
  return post(`/system/channel/${id}/test`)
}

/** 部门未映射记录 */
export interface DeptUnmapped {
  id: number
  channelCode: string
  deptId: string
  deptName: string
  deptPath: string
  sampleChannelUserId: string
  hitCount: number
  firstSeenAt: string
  lastSeenAt: string
}

export function pageDeptUnmapped(params: { current: number; size: number; channelCode?: string }): Promise<PageResult<DeptUnmapped>> {
  return get('/system/channel/dept-unmapped/page', params)
}

export function deleteDeptUnmapped(id: number): Promise<void> {
  return del(`/system/channel/dept-unmapped/${id}`)
}
