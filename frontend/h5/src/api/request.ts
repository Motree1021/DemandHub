import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { showToast } from 'vant'

/** 自定义配置：silent=true 时业务错误不弹 toast（用于探测接口后本地兜底的场景） */
declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean
  }
}

/**
 * 后端统一返回体结构
 */
export interface Result<T = unknown> {
  code: number
  message: string
  data: T
}

const TOKEN_KEY = 'demandhub_h5_token'
const REFRESH_KEY = 'demandhub_h5_refresh_token'

/** API 前缀：本地/同域 nginx 为 '/api'，H5 Publish TEST(Kong 路径前缀)经 VITE_API_BASE 注入 */
export const API_BASE: string = import.meta.env.VITE_API_BASE || '/api'

const service: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

service.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

let refreshing: Promise<boolean> | null = null

async function tryRefresh(): Promise<boolean> {
  const refreshTokenValue = localStorage.getItem(REFRESH_KEY)
  if (!refreshTokenValue) {
    return false
  }
  try {
    const resp = await axios.post<Result<{ accessToken: string; refreshToken: string }>>(
      `${API_BASE}/system/auth/refresh`,
      { refreshToken: refreshTokenValue }
    )
    if (resp.data.code === 0) {
      localStorage.setItem(TOKEN_KEY, resp.data.data.accessToken)
      localStorage.setItem(REFRESH_KEY, resp.data.data.refreshToken)
      return true
    }
  } catch {
    // 刷新失败，视为会话失效
  }
  return false
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

service.interceptors.response.use(
  async (response: AxiosResponse<Result>) => {
    // blob 响应（附件下载/预览）直接透传，不走统一返回体解析
    if (response.config.responseType === 'blob') {
      return response as never
    }
    const res = response.data
    if (res.code === 0) {
      return res.data as never
    }
    if (res.code === 401) {
      refreshing = refreshing || tryRefresh().finally(() => {
        refreshing = null
      })
      if (await refreshing) {
        return service.request(response.config) as never
      }
      clearSession()
      // 会话失效：重新走静默授权（重新加载当前页，路由守卫会引导授权）
      window.location.reload()
      return Promise.reject(new Error(res.message))
    }
    if (!response.config.silent) {
      showToast(res.message || '请求失败')
    }
    return Promise.reject(new Error(res.message))
  },
  async (error) => {
    // 网关 AuthFilter 返回真 HTTP 401：同样先刷新令牌重发，失败再重新授权
    const status = error.response?.status
    const config = error.config as (AxiosRequestConfig & { __retried401?: boolean }) | undefined
    if (status === 401 && config && !config.__retried401) {
      refreshing = refreshing || tryRefresh().finally(() => {
        refreshing = null
      })
      if (await refreshing) {
        config.__retried401 = true
        return service.request(config)
      }
      clearSession()
      // 会话失效：重新走静默授权（重新加载当前页，路由守卫会引导授权）
      window.location.reload()
      return Promise.reject(error)
    }
    if (!error.config?.silent) {
      showToast(error.response?.data?.message || error.message || '网络异常')
    }
    return Promise.reject(error)
  }
)

export function get<T = unknown>(url: string, params?: object, config?: AxiosRequestConfig): Promise<T> {
  return service.get(url, { ...config, params }) as unknown as Promise<T>
}

export function post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return service.post(url, data, config) as unknown as Promise<T>
}

export function put<T = unknown>(url: string, data?: unknown): Promise<T> {
  return service.put(url, data) as unknown as Promise<T>
}

export function del<T = unknown>(url: string): Promise<T> {
  return service.delete(url) as unknown as Promise<T>
}

export default service
