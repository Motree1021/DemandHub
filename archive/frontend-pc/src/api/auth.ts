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
  channel: string | null
  roles: string[]
  typeScopes: string[]
  grants: GrantVO[]
  mustChangePassword: boolean
  readOnly: boolean
}

export interface LoginResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  channel: string
  mustChangePassword: boolean
  user: UserInfo
}

/** PC 账密登录（连续失败 5 次锁 15 分钟；password_updated_at=NULL 首登强制改密） */
export function login(loginName: string, password: string): Promise<LoginResponse> {
  return post('/system/auth/login', { loginName, password })
}

/** 修改密码（强制改密/自助改密；改密后全清会话需重新登录） */
export function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  return post('/system/auth/change-password', { oldPassword, newPassword })
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
