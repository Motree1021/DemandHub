import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { describe, expect, it, vi } from 'vitest'
import service, { TOKEN_KEY } from '@/api/request'

describe('真实Axios interceptor的401身份保护', () => {
  it.each(['http', 'business'])('当前Bearer的%s401仍清当前JWT并发失效事件', async kind => {
    localStorage.setItem(TOKEN_KEY, 'synthetic-current-jwt')
    const expired = vi.fn(); window.addEventListener('demandhub:unauthorized', expired)
    try {
      await expect(service.get('/auth/me', { silent: true, adapter: config => {
        expect(config.headers.get('Authorization')).toBe('Bearer synthetic-current-jwt')
        const response: AxiosResponse = { config, status: kind === 'http' ? 401 : 200, statusText: '', headers: new AxiosHeaders(), data: { code: 401, message: '登录已过期', data: null } }
        return kind === 'http' ? Promise.reject(new AxiosError('unauthorized', 'ERR_BAD_REQUEST', config, undefined, response)) : Promise.resolve(response)
      } })).rejects.toMatchObject({ code: 401 })
      expect(localStorage.getItem(TOKEN_KEY)).toBeNull(); expect(expired).toHaveBeenCalledOnce()
    } finally { window.removeEventListener('demandhub:unauthorized', expired) }
  })
  it.each(['http', 'business'])('旧Bearer迟到%s401不删除新JWT或触发重登', async kind => {
    localStorage.setItem(TOKEN_KEY, 'synthetic-old-jwt')
    const expired = vi.fn(); window.addEventListener('demandhub:unauthorized', expired)
    let complete!: (response: AxiosResponse) => void
    let captured!: InternalAxiosRequestConfig
    let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    const request = service.get('/auth/me', { silent: true, adapter: config => {
      captured = config; entered()
      return new Promise((resolve, reject) => { complete = response => kind === 'http' ? reject(new AxiosError('unauthorized', 'ERR_BAD_REQUEST', config, undefined, response)) : resolve(response) })
    } })
    try {
      await started
      expect(captured.headers.get('Authorization')).toBe('Bearer synthetic-old-jwt')
      localStorage.setItem(TOKEN_KEY, 'synthetic-new-jwt')
      complete({ config: captured, status: kind === 'http' ? 401 : 200, statusText: '', headers: new AxiosHeaders(), data: { code: 401, message: '登录已过期', data: null } })
      await expect(request).rejects.toMatchObject({ code: 401 })
      expect(localStorage.getItem(TOKEN_KEY)).toBe('synthetic-new-jwt'); expect(expired).not.toHaveBeenCalled()
    } finally { window.removeEventListener('demandhub:unauthorized', expired) }
  })
  it.each(['http', 'business'])('无Bearer入口迟到%s401不删除新JWT', async kind => {
    const expired = vi.fn(); window.addEventListener('demandhub:unauthorized', expired)
    let complete!: (response: AxiosResponse) => void
    let captured!: InternalAxiosRequestConfig
    let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    const request = service.post('/auth/channel-parameters', { userid: 'synthetic-user', authToken: 'synthetic-host-token', userName: 'test' }, { silent: true, adapter: config => {
      captured = config; entered()
      return new Promise((resolve, reject) => { complete = response => kind === 'http' ? reject(new AxiosError('unauthorized', 'ERR_BAD_REQUEST', config, undefined, response)) : resolve(response) })
    } })
    try {
      await started
      expect(captured.headers.get('Authorization')).toBeUndefined()
      localStorage.setItem(TOKEN_KEY, 'synthetic-new-jwt')
      complete({ config: captured, status: kind === 'http' ? 401 : 200, statusText: '', headers: new AxiosHeaders(), data: { code: 401, message: '入口认证失败', data: null } })
      await expect(request).rejects.toMatchObject({ code: 401 })
      expect(localStorage.getItem(TOKEN_KEY)).toBe('synthetic-new-jwt'); expect(expired).not.toHaveBeenCalled()
    } finally { window.removeEventListener('demandhub:unauthorized', expired) }
  })
})
