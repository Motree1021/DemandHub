import { get, post } from './request'
export interface UserInfo {
  id: number; userId: string; name: string; deptName: string | null; deptPath: string | null
  channel: string; isAdmin: boolean
}
export interface LoginResponse { accessToken: string; tokenType: string; expiresIn: number; user: UserInfo }
export function channelSso(channel: string, ticket: string, state?: string): Promise<LoginResponse> {
  return get('/auth/channel-sso', { channel, ticket, ...(state ? { state } : {}) }, { silent: true })
}
export function me(): Promise<UserInfo> { return get('/auth/me', undefined, { silent: true }) }
export function devLogin(name: string, wecomUserid: string): Promise<LoginResponse> {
  return post('/auth/dev-login', { name, wecomUserid })
}
