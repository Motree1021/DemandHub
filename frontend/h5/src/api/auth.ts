import { get, post } from './request'

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
  /** 登录渠道（WEB/CHUANGJIN_LS），以服务端判定为准 */
  channel: string | null
  roles: string[]
  typeScopes: string[]
  grants: GrantVO[]
  mustChangePassword?: boolean
  readOnly: boolean
}

export interface LoginResponse {
  accessToken: string
  refreshToken: string
  expiresIn: number
  channel: string
  mustChangePassword?: boolean
  user: UserInfo
}

/**
 * 渠道 SSO 票据登录（对接标准 v2.1 §3.1/3.3）：
 * URL 只带 ticket/from/state；channel 由后端白名单校验（from=chuangjinls → CHUANGJIN_LS），
 * 身份字段仅经服务端 verify 响应返回，URL 明文身份一律不读不采信。
 */
export function channelSso(channel: string, ticket: string, state?: string): Promise<LoginResponse> {
  const params: Record<string, string> = { channel, ticket }
  if (state) {
    params.state = state
  }
  // silent：失败由 /auth 错误页统一呈现 AC07 文案，不再弹 toast
  return get('/system/auth/channel-sso', params, { silent: true })
}

/** 当前登录用户信息 */
export function me(): Promise<UserInfo> {
  return get('/system/auth/me')
}

/* ---------------- dev 专用：Mock 创金零售入口（模拟其首页签票跳转） ---------------- */

export interface MockChannelUser {
  channelUserId: string
  name: string
  orgName: string | null
}

/** Mock 创金零售可选用户（已建 CHUANGJIN_LS 映射的 ACTIVE 用户） */
export function mockSsoEntry(): Promise<MockChannelUser[]> {
  return get('/system/mock-sso/entry')
}

export interface IssuedTicket {
  ticket: string
  expiresIn: number
}

/** Mock 签发一次性 ticket（60s），随后按对接标准跳入 /h5/report?from=chuangjinls&ticket=xxx */
export function mockIssueTicket(channelUserId: string): Promise<IssuedTicket> {
  return post('/system/mock-sso/ticket', { channelUserId })
}
