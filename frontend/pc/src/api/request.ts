import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

/**
 * 后端统一返回体结构
 */
export interface Result<T = unknown> {
  code: number
  message: string
  data: T
}

const TOKEN_KEY = 'demandhub_token'
const REFRESH_KEY = 'demandhub_refresh_token'

const service: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// 请求拦截器：携带 token
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

/** 刷新中的 Promise，避免并发 401 时重复刷新 */
let refreshing: Promise<boolean> | null = null

/** 尝试用 refreshToken 换新 accessToken；成功返回 true */
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

function toLogin() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

// 响应拦截器：拆包统一返回体；401 先刷新令牌重发，失败再跳登录
service.interceptors.response.use(
  async (response: AxiosResponse<Result>) => {
    // 二进制下载/预览（responseType=blob）不是统一返回体，直接透传
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
        // 刷新成功，携带新 token 重发原请求
        return service.request(response.config) as never
      }
      toLogin()
      return Promise.reject(new Error(res.message))
    }
    ElMessage.error(res.message || '请求失败')
    return Promise.reject(new Error(res.message))
  },
  (error) => {
    const msg = error.response?.data?.message || error.message || '网络异常'
    ElMessage.error(msg)
    return Promise.reject(error)
  }
)

export function get<T = unknown>(url: string, params?: object): Promise<T> {
  return service.get(url, { params }) as unknown as Promise<T>
}

export function post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
  return service.post(url, data, config) as unknown as Promise<T>
}

export function put<T = unknown>(url: string, data?: unknown): Promise<T> {
  return service.put(url, data) as unknown as Promise<T>
}

export function del<T = unknown>(url: string, params?: object): Promise<T> {
  return service.delete(url, { params }) as unknown as Promise<T>
}

export default service
