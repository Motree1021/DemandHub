import axios from 'axios'
import type { AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'

declare module 'axios' { interface AxiosRequestConfig { silent?: boolean; _retried?: boolean } }

export interface Result<T = unknown> { code: number; message: string; data: T }
export class ApiError extends Error {
  constructor(public code: number, message: string) { super(message); this.name = 'ApiError' }
}

export const API_BASE: string = import.meta.env.VITE_API_BASE || '/demandhub-api'
const ACCESS_KEY = 'demandhub_admin_access'
const REFRESH_KEY = 'demandhub_admin_refresh'

export function getAccessToken() { return localStorage.getItem(ACCESS_KEY) }
export function getRefreshToken() { return localStorage.getItem(REFRESH_KEY) }
export function saveTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

/** 会话彻底失效：清票并通知路由守卫跳登录页。 */
export function expireSession() {
  clearTokens()
  window.dispatchEvent(new Event('demandhub-admin:unauthorized'))
}

const service = axios.create({ baseURL: API_BASE, timeout: 30000 })
service.interceptors.request.use(config => {
  const token = getAccessToken()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  return config
})

// 401 无感续期：用 refresh token 换新票并重放原请求；并发请求共享同一次续期（单飞）
let refreshing: Promise<boolean> | null = null
async function tryRefresh(): Promise<boolean> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return false
  try {
    const resp = await axios.post<Result<{ accessToken: string; refreshToken: string }>>(
      `${API_BASE}/auth/refresh`, { refreshToken }, { timeout: 30000 })
    if (resp.data.code !== 0) return false
    saveTokens(resp.data.data.accessToken, resp.data.data.refreshToken)
    return true
  } catch { return false }
}

function isRefreshCall(config?: InternalAxiosRequestConfig) {
  return (config?.url || '').includes('/auth/refresh')
}

async function handle401(config?: InternalAxiosRequestConfig): Promise<unknown> {
  if (!config || config._retried || isRefreshCall(config)) { expireSession(); throw new ApiError(401, '登录已过期') }
  config._retried = true
  refreshing = refreshing || tryRefresh().finally(() => { refreshing = null })
  if (await refreshing) return service(config)
  expireSession()
  throw new ApiError(401, '登录已过期')
}

service.interceptors.response.use(response => {
  const res = response.data as Result
  if (res.code === 0) return res.data as never
  if (res.code === 401) return handle401(response.config) as never
  return Promise.reject(new ApiError(res.code, res.message || '请求失败'))
}, error => {
  const code = error.response?.data?.code || error.response?.status || -1
  const message = error.response?.data?.message || error.message || '网络异常'
  if (code === 401) return handle401(error.config) as never
  return Promise.reject(new ApiError(code, message))
})

export function get<T>(url: string, params?: object, config?: AxiosRequestConfig): Promise<T> {
  return service.get(url, { ...config, params }) as unknown as Promise<T>
}
export function post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return service.post(url, data, config) as unknown as Promise<T>
}
export function put<T>(url: string, data?: unknown): Promise<T> {
  return service.put(url, data) as unknown as Promise<T>
}
export function patch<T>(url: string, data?: unknown): Promise<T> {
  return service.patch(url, data) as unknown as Promise<T>
}
export function del<T>(url: string): Promise<T> {
  return service.delete(url) as unknown as Promise<T>
}

/** 附件下载：携带登录票拉 blob 并触发浏览器保存（服务端业务错误按 JSON 返回，须识别后按统一口径抛出）。 */
export async function downloadFile(url: string, fileName: string) {
  const token = getAccessToken()
  const resp = await fetch(`${API_BASE}${url}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  const contentType = resp.headers.get('content-type') || ''
  if (!resp.ok || contentType.includes('json')) {
    const result = await resp.json().catch(() => null) as Result | null
    const code = result?.code || resp.status
    if (code === 401) expireSession()
    throw new ApiError(code, result?.message || '下载失败')
  }
  const blobUrl = URL.createObjectURL(await resp.blob())
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(blobUrl)
}
export default service
