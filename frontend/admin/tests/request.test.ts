import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

import service, { clearTokens, get, saveTokens } from '@/api/request'

// 只替换传输层（adapter），拦截器链路保持真实执行
const serviceAdapter = vi.fn<AxiosAdapter>()
const rootAdapter = vi.fn<AxiosAdapter>()

function ok(config: InternalAxiosRequestConfig, data: unknown): AxiosResponse {
  return { data, status: 200, statusText: 'OK', headers: {}, config }
}
function bizError(config: InternalAxiosRequestConfig, code: number, message: string): Promise<never> {
  // eslint-disable-next-line @typescript-eslint/no-throw-literal
  throw { config, response: ok(config, { code, message, data: null }) }
}

beforeEach(() => {
  clearTokens()
  serviceAdapter.mockReset()
  rootAdapter.mockReset()
  service.defaults.adapter = serviceAdapter
  axios.defaults.adapter = rootAdapter
})

describe('request 统一响应体拦截', () => {
  it('code=0 时直接解出 data', async () => {
    serviceAdapter.mockImplementation(async config => ok(config, { code: 0, message: 'success', data: { a: 1 } }))
    await expect(get<{ a: number }>('/x')).resolves.toEqual({ a: 1 })
  })

  it('业务错误抛 ApiError 且带业务码', async () => {
    serviceAdapter.mockImplementation(async config => bizError(config, 1120, '登录账号已存在'))
    await expect(get('/x')).rejects.toMatchObject({ code: 1120, message: '登录账号已存在' })
  })
})

describe('401 无感续期', () => {
  it('401 时用 refresh token 换新票并重放原请求', async () => {
    saveTokens('expired-access', 'good-refresh')
    serviceAdapter
      .mockImplementationOnce(async config => bizError(config, 401, 'expired'))
      .mockImplementationOnce(async config => ok(config, { code: 0, message: 'success', data: { name: '管理员' } }))
    rootAdapter.mockImplementation(async config =>
      ok(config, { code: 0, message: 'success', data: { accessToken: 'new-access', refreshToken: 'new-refresh' } }))

    await expect(get('/me')).resolves.toEqual({ name: '管理员' })
    expect(rootAdapter).toHaveBeenCalledOnce()
    expect(JSON.parse(String(rootAdapter.mock.calls[0][0].data))).toEqual({ refreshToken: 'good-refresh' })
    expect(localStorage.getItem('demandhub_admin_access')).toBe('new-access')
    expect(localStorage.getItem('demandhub_admin_refresh')).toBe('new-refresh')
    // 重放的原请求带新 access token
    const replay = serviceAdapter.mock.calls[1][0]
    expect(String(replay.headers.get?.('Authorization') ?? replay.headers.Authorization)).toBe('Bearer new-access')
  })

  it('续期失败则清票并抛 401', async () => {
    saveTokens('expired-access', 'bad-refresh')
    serviceAdapter.mockImplementation(async config => bizError(config, 401, 'expired'))
    rootAdapter.mockImplementation(async config => ok(config, { code: 1117, message: '登录已过期', data: null }))

    await expect(get('/me')).rejects.toMatchObject({ code: 401 })
    expect(localStorage.getItem('demandhub_admin_access')).toBeNull()
    expect(localStorage.getItem('demandhub_admin_refresh')).toBeNull()
  })

  it('refresh 接口自身 401 不进入续期死循环', async () => {
    saveTokens('a', 'r')
    rootAdapter.mockImplementation(async config => bizError(config, 401, 'expired'))
    serviceAdapter.mockImplementation(async config => bizError(config, 401, 'expired'))

    await expect(get('/me')).rejects.toMatchObject({ code: 401 })
    expect(rootAdapter).toHaveBeenCalledOnce() // 只尝试续期一次
  })
})
