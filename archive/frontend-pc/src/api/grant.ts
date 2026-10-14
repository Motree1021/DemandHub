import { get, post, put, del } from './request'

/** 业务角色授权记录（角色族 ADMIN/EXECUTIVE/MANAGER/HANDLER） */
export interface RoleGrant {
  id: number
  /** 被授权用户 OneID */
  demandUserId: number
  roleCode: string
  orgId: number | null
  /** 需求类型集合（逗号多选），null=跟随角色默认 */
  demandTypeScope: string | null
  effectiveFrom: string | null
  effectiveTo: string | null
  /** 授权人 OneID */
  grantedBy: number | null
  createdAt: string
}

export interface RoleGrantSaveRequest {
  id?: number
  /** 被授权用户 OneID（必填） */
  demandUserId: number | null
  roleCode: string
  orgId?: number | null
  demandTypeScope?: string | null
  effectiveFrom?: string | null
  effectiveTo?: string | null
}

export interface PageResult<T> {
  records: T[]
  total: number
  size: number
  current: number
  pages: number
}

/** 授权分页查询（仅 ADMIN） */
export function pageGrants(params: { current: number; size: number; demandUserId?: number; roleCode?: string }): Promise<PageResult<RoleGrant>> {
  return get('/system/grant/page', params as Record<string, unknown>)
}

/** 新增授权 */
export function createGrant(data: RoleGrantSaveRequest): Promise<number> {
  return post('/system/grant', data)
}

/** 修改授权 */
export function updateGrant(id: number, data: RoleGrantSaveRequest): Promise<void> {
  return put(`/system/grant/${id}`, data)
}

/** 回收授权 */
export function deleteGrant(id: number): Promise<void> {
  return del(`/system/grant/${id}`)
}

/** 用户分页（授权时选人，仅 ADMIN） */
export interface UserSnapshotVO {
  id: number
  userId: string
  name: string
  primaryOrgId: number | null
  deptPath: string | null
  status: string
}

export function pageUsers(params: { current: number; size: number; keyword?: string; status?: string }): Promise<PageResult<UserSnapshotVO>> {
  return get('/system/user/page', params as Record<string, unknown>)
}

/** 组织树 */
export interface OrgNode {
  orgId: number
  name: string
  level: string
  parentId: number
  path: string
  orgKind: string | null
  /** 渠道外部部门ID（回流校准用） */
  externalDeptId?: string | null
  status?: string
  children?: OrgNode[]
}

export function orgTree(): Promise<OrgNode[]> {
  return get('/system/org/tree')
}
