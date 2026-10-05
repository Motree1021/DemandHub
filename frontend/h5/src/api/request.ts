import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { showToast } from 'vant'

declare module 'axios' { interface AxiosRequestConfig { silent?: boolean } }
export interface Result<T = unknown> { code: number; message: string; data: T }
export const TOKEN_KEY = 'demandhub_h5_token'
export const API_BASE: string = import.meta.env.VITE_API_BASE || '/demandhub-api'
export class ApiError extends Error {
  constructor(public code: number, message: string) { super(message); this.name = 'ApiError' }
}
export function expireSession() {
  localStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event('demandhub:unauthorized'))
}
export function bearerHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}
/** 迟到的旧账号401或无Bearer入口响应，不能删除后来登录的新账号JWT。 */
function expireRequestSession(config?: AxiosRequestConfig) {
  const headers = config?.headers
  const authorization = headers instanceof axios.AxiosHeaders
    ? headers.get('Authorization')
    : headers?.Authorization || headers?.authorization
  const currentToken = localStorage.getItem(TOKEN_KEY)
  if (currentToken && authorization === `Bearer ${currentToken}`) expireSession()
}
const service = axios.create({ baseURL: API_BASE, timeout: 30000 })
service.interceptors.request.use(config => {
  Object.assign(config.headers, bearerHeaders())
  return config
})
service.interceptors.response.use(response => {
  const res = response.data as Result
  if (res.code === 0) return res.data as never
  if (res.code === 401) expireRequestSession(response.config)
  if (!response.config.silent && res.code !== 401) showToast(res.message || '请求失败')
  return Promise.reject(new ApiError(res.code, res.message || '请求失败'))
}, error => {
  const code = error.response?.data?.code || error.response?.status || -1
  const message = error.response?.data?.message || error.message || '网络异常'
  if (code === 401) expireRequestSession(error.config)
  if (!error.config?.silent && code !== 401) showToast(message)
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

/** 文件下载同样携带 Bearer，并识别 HTTP 200 的业务错误。 */
export async function downloadFile(path: string, fallbackName: string, params?: Record<string, string>) {
  const query = new URLSearchParams(params).toString()
  const response = await fetch(`${API_BASE}${path}${query ? `?${query}` : ''}`, { headers: bearerHeaders() })
  const contentType = response.headers.get('content-type') || ''
  if (!response.ok || contentType.includes('json')) {
    const result = await response.json().catch(() => null) as Result | null
    const code = result?.code || response.status
    if (code === 401) expireSession()
    throw new ApiError(code, result?.message || '下载失败')
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  let filename = fallbackName
  try { filename = encoded ? decodeURIComponent(encoded) : plain || fallbackName } catch { /* 使用安全回退名 */ }
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename.replace(/[\/\\]/g, '_')
  document.body.append(anchor)
  try { anchor.click() } finally { anchor.remove(); setTimeout(() => URL.revokeObjectURL(objectUrl), 1000) }
}
export default service
