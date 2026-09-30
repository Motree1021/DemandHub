import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ channelSso: vi.fn(), me: vi.fn(), devLogin: vi.fn(), user: { isLoggedIn: false, userInfo: null as { id: number; isAdmin: boolean } | null, setFrom: vi.fn(), setLogin: vi.fn(), setUserInfo: vi.fn(), clear: vi.fn() } }))
vi.mock('@/api/auth', () => ({ channelSso: mocks.channelSso, me: mocks.me, devLogin: mocks.devLogin }))
vi.mock('@/store/user', () => ({ useUserStore: () => mocks.user }))
beforeEach(() => {
  vi.resetModules(); vi.clearAllMocks()
  history.replaceState({}, '', '/h5-preview/random/#/auth')
  mocks.user.isLoggedIn = false; mocks.user.userInfo = null
  mocks.user.setLogin.mockImplementation(response => { mocks.user.isLoggedIn = true; mocks.user.userInfo = response.user })
  mocks.user.setUserInfo.mockImplementation(user => { mocks.user.userInfo = user })
  mocks.user.clear.mockImplementation(() => { mocks.user.isLoggedIn = false; mocks.user.userInfo = null })
})
describe('渠道hash入口与管理员路由', () => {
  it('实际守卫读取外层票据，认证后保留草稿hash并清除两处参数', async () => {
    history.replaceState({}, '', '/h5-preview/random/?from=chuangjinls&ticket=outer&state=a&theme=light#/report?draftId=9&ticket=inner')
    mocks.channelSso.mockResolvedValue({ accessToken: 'fake-token', user: { id: 1, isAdmin: false } })
    const { default: router } = await import('@/router')
    await router.push('/report?draftId=9&ticket=inner')
    expect(mocks.channelSso).toHaveBeenCalledOnce()
    expect(mocks.channelSso).toHaveBeenCalledWith('chuangjinls', 'outer', 'a')
    expect(router.currentRoute.value.query).toEqual({ draftId: '9' })
    expect(location.search).toBe('?theme=light'); expect(location.hash).toBe('#/report?draftId=9')
    router.options.history.destroy()
  })
  it('票据失败也清敏感参数并显示重入提示，不重复消费', async () => {
    history.replaceState({}, '', '/h5/random/?ticket=expired#/report?ticket=expired')
    mocks.channelSso.mockRejectedValue(new Error('登录已失效，请从创金零售重新进入'))
    const { default: router } = await import('@/router')
    await router.push('/report?ticket=expired')
    expect(router.currentRoute.value.path).toBe('/auth')
    expect(location.href).not.toContain('ticket='); expect(mocks.channelSso).toHaveBeenCalledOnce()
    router.options.history.destroy()
  })
  it('普通人不能停留管理员整理路由，管理员可进入', async () => {
    mocks.user.isLoggedIn = true; mocks.user.userInfo = { id: 1, isAdmin: false }
    const { default: router } = await import('@/router')
    await router.push('/admin'); expect(router.currentRoute.value.path).toBe('/mine')
    mocks.user.userInfo.isAdmin = true
    await router.push('/admin'); expect(router.currentRoute.value.path).toBe('/admin')
    router.options.history.destroy()
  })
  it('身份恢复失败清登录态，跳auth一次而非reload循环', async () => {
    mocks.user.isLoggedIn = true; mocks.me.mockRejectedValue(new Error('过期'))
    const { default: router } = await import('@/router')
    await router.push('/mine')
    expect(router.currentRoute.value.path).toBe('/auth'); expect(mocks.me).toHaveBeenCalledOnce(); expect(mocks.user.clear).toHaveBeenCalledOnce()
    router.options.history.destroy()
  })
})
