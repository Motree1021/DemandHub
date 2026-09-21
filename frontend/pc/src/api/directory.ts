import { get } from './request'
import { pageUsers, type UserSnapshotVO, type OrgNode, orgTree } from './grant'
import { listDemandTypes, type DemandTypeItem } from './admin'

export type { UserSnapshotVO, OrgNode, DemandTypeItem }
export { orgTree }

/**
 * 一期 Mock 环境的用户目录兜底：
 * 后端 /system/user/page 限 ADMIN，非管理员选人（分派/@人/代办提报）时无可用查询接口。
 * 这里先试调真实接口，403 时回退到与 Mock 权限中心一致的 7 个内置用户。
 * 二期对接真实权限中心后该兜底自然失效（接口会对全员开放）。
 */
const MOCK_USERS: UserSnapshotVO[] = [
  { id: 1001, userId: 'u_admin_001', name: '张管理', primaryOrgId: 110, deptPath: '创金合信零售业务线/财管科技产品部', status: 'ACTIVE' },
  { id: 1002, userId: 'u_exec_001', name: '李总', primaryOrgId: 100, deptPath: '创金合信零售业务线', status: 'ACTIVE' },
  { id: 1003, userId: 'u_mgr_tech', name: '王经理', primaryOrgId: 110, deptPath: '创金合信零售业务线/财管科技产品部', status: 'ACTIVE' },
  { id: 1004, userId: 'u_handler_a1', name: '陈陪伴', primaryOrgId: 121, deptPath: '创金合信零售业务线/客户陪伴服务部/客户陪伴一组', status: 'ACTIVE' },
  { id: 1005, userId: 'u_handler_b1', name: '刘培训', primaryOrgId: 131, deptPath: '创金合信零售业务线/培训开发部/培训开发一组', status: 'ACTIVE' },
  { id: 1006, userId: 'u_reporter_1', name: '赵一线', primaryOrgId: 141, deptPath: '创金合信零售业务线/零售一线营业部/营业部一组', status: 'ACTIVE' },
  { id: 1007, userId: 'u_reporter_2', name: '钱一线', primaryOrgId: 141, deptPath: '创金合信零售业务线/零售一线营业部/营业部一组', status: 'ACTIVE' }
]

let cachedUsers: UserSnapshotVO[] | null = null

/** 全量用户目录（管理员走真实接口，其他角色回退 Mock 目录） */
export async function listAllUsers(force = false): Promise<UserSnapshotVO[]> {
  if (cachedUsers && !force) {
    return cachedUsers
  }
  try {
    const page = await pageUsers({ current: 1, size: 500 })
    cachedUsers = page.records
  } catch {
    cachedUsers = MOCK_USERS
  }
  return cachedUsers
}

/** 按关键字检索用户（匹配姓名/userId） */
export async function searchUsers(keyword: string): Promise<UserSnapshotVO[]> {
  const all = await listAllUsers()
  if (!keyword) {
    return all
  }
  const kw = keyword.toLowerCase()
  return all.filter((u) => u.name.toLowerCase().includes(kw) || u.userId.toLowerCase().includes(kw))
}

/** 内置需求类型兜底（非 ADMIN 访问不了类型字典管理接口时使用） */
const DEFAULT_TYPES: DemandTypeItem[] = [
  { id: -1, typeCode: 'TECH', typeName: '科技需求', parentTypeCode: null, defaultOrgId: 111, stateMachineKey: 'DEFAULT', slaConfig: null, sort: 1, status: 'ACTIVE' },
  { id: -2, typeCode: 'MATL', typeName: '物料需求', parentTypeCode: null, defaultOrgId: 121, stateMachineKey: 'DEFAULT', slaConfig: null, sort: 2, status: 'ACTIVE' },
  { id: -3, typeCode: 'TRAIN', typeName: '培训需求', parentTypeCode: null, defaultOrgId: 131, stateMachineKey: 'DEFAULT', slaConfig: null, sort: 3, status: 'ACTIVE' }
]

let cachedTypes: DemandTypeItem[] | null = null

/** 启用的需求类型列表（ADMIN 取字典管理接口，其他角色回退内置三类型） */
export async function listActiveTypes(force = false): Promise<DemandTypeItem[]> {
  if (cachedTypes && !force) {
    return cachedTypes
  }
  try {
    const all = await listDemandTypes()
    cachedTypes = all.filter((t) => t.status === 'ACTIVE').sort((a, b) => a.sort - b.sort)
  } catch {
    cachedTypes = DEFAULT_TYPES
  }
  return cachedTypes
}

/** 平铺组织列表 */
export interface OrgFlat {
  id: number
  orgId: number
  name: string
  level: string
  parentId: number
  path: string
  orgKind: string | null
  status: string
}

export function listOrgs(): Promise<OrgFlat[]> {
  return get('/system/org/list')
}
