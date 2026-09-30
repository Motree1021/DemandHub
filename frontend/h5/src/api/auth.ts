import { get, post } from './request'
export interface UserInfo {
  id: number; userId: string; name: string; deptName: string | null; deptPath: string | null
  channel: string; isAdmin: boolean
}
export interface ChannelParameters { userid: string; authToken: string; userName: string; department?: string }
/** 识别入口不代表后端启用；宿主token仅经请求体交换，不写入登录store。 */
export function channelParameters(parameters: ChannelParameters): Promise<LoginResponse> {
  return post('/auth/channel-parameters', parameters, { silent: true })
}
export interface LoginResponse { accessToken: string; tokenType: string; expiresIn: number; user: UserInfo }
export function channelSso(channel: string, ticket: string, state?: string): Promise<LoginResponse> {
  return get('/auth/channel-sso', { channel, ticket, ...(state ? { state } : {}) }, { silent: true })
}
export function me(): Promise<UserInfo> { return get('/auth/me', undefined, { silent: true }) }
export function devLogin(name: string, wecomUserid: string): Promise<LoginResponse> {
  return post('/auth/dev-login', { name, wecomUserid })
}
