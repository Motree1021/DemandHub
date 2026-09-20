import { get, post } from './request'

/** 登录用户信息（含生效授权明细） */
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

/** 一期 Mock：登录页可选用户列表（二期替换为企微扫码） */
export function listMockUsers(): Promise<MockUser[]> {
  return get('/system/auth/mock-users')
}

/** 企微回调登录（PC 扫码；一期 code 为 mock-{userId}） */
export function loginByCode(code: string): Promise<LoginResponse> {
  return get('/system/auth/callback', { code })
}

/** 刷新访问令牌 */
export function refreshToken(refreshTokenValue: string): Promise<LoginResponse> {
  return post('/system/auth/refresh', { refreshToken: refreshTokenValue })
}

/** 登出 */
export function logout(refreshTokenValue: string): Promise<void> {
  return post(`/system/auth/logout?refreshToken=${encodeURIComponent(refreshTokenValue)}`)
}

/** 当前登录用户信息 */
export function me(): Promise<UserInfo> {
  return get('/system/auth/me')
}
