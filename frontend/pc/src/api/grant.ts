import { get, post, put, del } from './request'

/** 业务角色授权记录 */
export interface RoleGrant {
  id: number
  userId: string
  roleCode: string
  orgId: number | null
  demandTypeScope: string | null
  effectiveFrom: string | null
  effectiveTo: string | null
  grantedBy: string | null
  createdAt: string
}

export interface RoleGrantSaveRequest {
  id?: number
  userId: string
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
export function pageGrants(params: { current: number; size: number; userId?: string; roleCode?: string }): Promise<PageResult<RoleGrant>> {
  return get('/system/grant/page', params)
}

/** 新增授权 */
export function createGrant(data: RoleGrantSaveRequest): Promise<number> {
  return post('/system/grant', data)
}

/** 修改授权 */
export function updateGrant(id: number, data: RoleGrantSaveRequest): Promise<void> {
  return put(`/system/grant/${id}`, data)
}

/** 删除授权 */
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

export function pageUsers(params: { current: number; size: number; keyword?: string }): Promise<PageResult<UserSnapshotVO>> {
  return get('/system/user/page', params)
}

/** 组织树 */
export interface OrgNode {
  orgId: number
  name: string
  level: string
  parentId: number
  path: string
  orgKind: string | null
  children?: OrgNode[]
}

export function orgTree(): Promise<OrgNode[]> {
  return get('/system/org/tree')
}
