import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { channelParameters, channelSso } from '@/api/auth'
import { useUserStore } from '@/store/user'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/api/request', () => ({ get: mocks.get, post: mocks.post, TOKEN_KEY: 'demandhub_h5_token' }))
beforeEach(() => { vi.clearAllMocks(); setActivePinia(createPinia()) })
describe('参数登录API和本系统JWT', () => {
  it('POST精确camelCase DTO，宿主Token只在body，本系统JWT才进store', async () => {
    const parameters = { userid: 'synthetic-user', authToken: 'synthetic-host-token', userName: '测试用户', department: '默认组织' }
    const response = { accessToken: 'synthetic-system-jwt', tokenType: 'Bearer', expiresIn: 28800, user: { id: 2, userId: 'synthetic-user', name: '测试用户', deptName: '默认组织', deptPath: null, channel: 'CHUANGJIN_LS', isAdmin: false } }
    mocks.post.mockResolvedValue(response)
    useUserStore().setLogin(await channelParameters(parameters))
    expect(mocks.post).toHaveBeenCalledWith('/auth/channel-parameters', parameters, { silent: true })
    expect(useUserStore().token).toBe('synthetic-system-jwt')
    expect(localStorage.getItem('demandhub_h5_token')).toBe('synthetic-system-jwt')
    expect(JSON.stringify(useUserStore().$state)).not.toContain('synthetic-host-token')
    expect(localStorage.getItem('X-Auth-Token')).toBeNull(); expect(localStorage.getItem('authToken')).toBeNull()
  })
  it('交换失败不自动调用其他登录接口', async () => {
    mocks.post.mockRejectedValue({ code: 404, message: 'Not Found' })
    await expect(channelParameters({ userid: 'synthetic-user', authToken: 'synthetic-host-token', userName: 'test' })).rejects.toMatchObject({ code: 404 })
    expect(mocks.post).toHaveBeenCalledOnce(); expect(mocks.get).not.toHaveBeenCalled()
  })
  it('legacy ticket调用不变', async () => {
    mocks.get.mockResolvedValue({})
    await channelSso('chuangjinls', 'synthetic-ticket', 'synthetic-state')
    expect(mocks.get).toHaveBeenCalledWith('/auth/channel-sso', { channel: 'chuangjinls', ticket: 'synthetic-ticket', state: 'synthetic-state' }, { silent: true })
    expect(mocks.post).not.toHaveBeenCalled()
  })
})
