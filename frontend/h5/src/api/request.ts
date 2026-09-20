import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { showToast } from 'vant'

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

const service: AxiosInstance = axios.create({
  baseURL: '/api',
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
      '/api/system/auth/refresh',
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
    showToast(res.message || '请求失败')
    return Promise.reject(new Error(res.message))
  },
  (error) => {
    showToast(error.response?.data?.message || error.message || '网络异常')
    return Promise.reject(error)
  }
)

export function get<T = unknown>(url: string, params?: Record<string, unknown>): Promise<T> {
  return service.get(url, { params }) as unknown as Promise<T>
}

export function post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return service.post(url, data, config) as unknown as Promise<T>
}

export default service
