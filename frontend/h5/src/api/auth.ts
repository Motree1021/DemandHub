import { get } from './request'

export interface GrantVO {
  roleCode: string
  orgId: number | null
  orgName: string
  demandTypeScope: string | null
}

export interface UserInfo {
  id: number
  userId: string
  name: string
  primaryOrgId: number | null
  orgName: string | null
  deptPath: string | null
  roles: string[]
  grants: GrantVO[]
  readOnly: boolean
}

export interface LoginResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  user: UserInfo
}

export interface MockUser {
  userId: string
  name: string
  orgName: string
  mockCode: string
}

/** 一期 Mock：可选用户列表（二期替换为企微静默授权） */
export function listMockUsers(): Promise<MockUser[]> {
  return get('/system/auth/mock-users')
}

/**
 * H5 静默授权登录（企微 webview 内）
 * @param code 企微授权码；一期 Mock：mock-{userId}
 * @param from 来源标记（创金零售 App 跳入时为 chuangjinls）
 */
export function silentLogin(code: string, from?: string): Promise<LoginResponse> {
  return get('/system/auth/silent', from ? { code, from } : { code })
}

/** 当前登录用户信息 */
export function me(): Promise<UserInfo> {
  return get('/system/auth/me')
}
