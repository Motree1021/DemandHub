import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ channelSso: vi.fn(), channelParameters: vi.fn(), me: vi.fn(), devLogin: vi.fn(), user: { isLoggedIn: false, userInfo: null as { id: number; isAdmin: boolean } | null, setFrom: vi.fn(), setLogin: vi.fn(), setUserInfo: vi.fn(), clear: vi.fn() } }))
vi.mock('@/api/auth', () => ({ channelSso: mocks.channelSso, channelParameters: mocks.channelParameters, me: mocks.me, devLogin: mocks.devLogin }))
vi.mock('@/store/user', () => ({ useUserStore: () => mocks.user }))
beforeEach(() => {
  vi.resetModules(); vi.clearAllMocks(); mocks.channelParameters.mockReset(); mocks.channelSso.mockReset()
  history.replaceState({}, '', '/h5-preview/random/#/auth')
  mocks.user.isLoggedIn = false; mocks.user.userInfo = null
  mocks.user.setLogin.mockImplementation(response => { mocks.user.isLoggedIn = true; mocks.user.userInfo = response.user })
  mocks.user.setUserInfo.mockImplementation(user => { mocks.user.userInfo = user })
  mocks.user.clear.mockImplementation(() => { mocks.user.isLoggedIn = false; mocks.user.userInfo = null })
})
describe('渠道hash入口与管理员路由', () => {
  it('实际守卫读取外层票据，认证后保留草稿hash并清除两处参数', async () => {
    history.replaceState({}, '', '/h5-preview/random/?from=chuangjinls&ticket=outer&state=a&theme=light#/report?draftId=9')
    mocks.channelSso.mockResolvedValue({ accessToken: 'fake-token', user: { id: 1, isAdmin: false } })
    const { default: router } = await import('@/router')
    await router.push('/report?draftId=9')
    expect(mocks.channelSso).toHaveBeenCalledOnce()
    expect(mocks.channelSso).toHaveBeenCalledWith('chuangjinls', 'outer', 'a')
    expect(router.currentRoute.value.query).toEqual({ draftId: '9' })
    expect(location.search).toBe('?theme=light'); expect(location.hash).toBe('#/report?draftId=9')
    router.options.history.destroy()
  })
  it('票据失败也清敏感参数并显示重入提示，不重复消费', async () => {
    history.replaceState({}, '', '/h5/random/?ticket=synthetic-expired#/report')
    mocks.channelSso.mockRejectedValue({ code: 1107, message: '上游错误原文' })
    const { default: router } = await import('@/router')
    await router.push('/report')
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

describe('宿主参数交换与立即清理', () => {
  const identity = 'userid=synthetic-user&X-Auth-Token=synthetic-host-token&userName=%E6%B5%8B%E8%AF%95&department=%E9%83%A8%E9%97%A8'
  it('初始化前清outer/hash与history，POST交换后只保留正常hash导航', async () => {
    history.replaceState({ current: '/report?X-Auth-Token=synthetic-host-token' }, '', `/h5-preview/random/?${identity}&theme=light#/report?draftId=9`)
    mocks.channelParameters.mockImplementation(async parameters => {
      expect(location.href).not.toContain('synthetic-host-token')
      expect(parameters).toEqual({ userid: 'synthetic-user', authToken: 'synthetic-host-token', userName: '测试', department: '部门' })
      return { accessToken: 'synthetic-system-jwt', user: { id: 3, isAdmin: false } }
    })
    const { default: router } = await import('@/router')
    expect(location.search).toBe('?theme=light')
    expect(JSON.stringify(history.state)).not.toContain('synthetic-host-token')
    await router.push('/report?draftId=9')
    expect(mocks.channelParameters).toHaveBeenCalledOnce()
    expect(mocks.user.setLogin).toHaveBeenCalledWith({ accessToken: 'synthetic-system-jwt', user: { id: 3, isAdmin: false } })
    expect(mocks.channelSso).not.toHaveBeenCalled(); expect(mocks.devLogin).not.toHaveBeenCalled()
    expect(router.currentRoute.value.fullPath).toBe('/report?draftId=9')
    await router.push('/mine'); expect(router.currentRoute.value.path).toBe('/mine')
    expect(mocks.channelParameters).toHaveBeenCalledOnce()
    router.options.history.destroy()
  })
  it('单一hash身份参数兼容且部门可省略', async () => {
    history.replaceState({}, '', '/h5/random/#/mine?userid=synthetic-user&X-Auth-Token=synthetic-host-token&userName=test')
    mocks.channelParameters.mockResolvedValue({ accessToken: 'synthetic-system-jwt', user: { id: 3, isAdmin: false } })
    const { default: router } = await import('@/router')
    expect(location.hash).toBe('#/mine')
    await router.push('/mine')
    expect(mocks.channelParameters).toHaveBeenCalledWith({ userid: 'synthetic-user', authToken: 'synthetic-host-token', userName: 'test' })
    router.options.history.destroy()
  })
  it.each([
    '?userid=synthetic-user#/report', '?department=test#/report',
    '?userid=synthetic-user&X-Auth-Token=&userName=test#/report',
    `?${identity}&userid=other#/report`, `?${identity}#/report?userid=other`,
    `?${identity}#/report?userid=synthetic-user`, `?${identity}&ticket=synthetic-ticket#/report`
  ])('不完整/重复/冲突/混合参数不开任何登录接口并清旧登录（%s）', async entry => {
    history.replaceState({}, '', `/h5/random/${entry}`)
    mocks.user.isLoggedIn = true; mocks.user.userInfo = { id: 4, isAdmin: true }
    const { default: router } = await import('@/router')
    expect(location.href).not.toContain('X-Auth-Token'); expect(location.href).not.toContain('userid=')
    await router.push('/report')
    expect(router.currentRoute.value.path).toBe('/auth')
    expect(mocks.channelParameters).not.toHaveBeenCalled(); expect(mocks.channelSso).not.toHaveBeenCalled(); expect(mocks.devLogin).not.toHaveBeenCalled()
    expect(mocks.user.isLoggedIn).toBe(false)
    expect(router.currentRoute.value.fullPath).not.toContain('synthetic-host-token')
    router.options.history.destroy()
  })
  it('404明确提示参数联调尚未开启，不fallback ticket或dev-login', async () => {
    history.replaceState({}, '', `/h5/random/?${identity}#/report`)
    mocks.channelParameters.mockRejectedValue({ code: 404, message: '未知响应含synthetic-host-token' })
    const { default: router } = await import('@/router')
    await router.push('/report')
    expect(router.currentRoute.value.query).toEqual({ error: '参数联调登录尚未开启' })
    expect(location.href).not.toContain('synthetic-host-token')
    expect(mocks.channelSso).not.toHaveBeenCalled(); expect(mocks.devLogin).not.toHaveBeenCalled()
    router.options.history.destroy()
  })
  it('错误原文即使含Token，也不会进入路由、存储或日志', async () => {
    const syntheticToken = 'synthetic-host-token'
    const logs = ['log', 'warn', 'error', 'info', 'debug'].map(method => vi.spyOn(console, method as 'log').mockImplementation(() => {}))
    const localWrites = vi.spyOn(localStorage, 'setItem'); const sessionWrites = vi.spyOn(sessionStorage, 'setItem')
    history.replaceState({}, '', `/h5/random/?${identity}#/report`)
    mocks.channelParameters.mockRejectedValue(new Error(`upstream rejected ${syntheticToken}`))
    const { default: router } = await import('@/router'); await router.push('/report')
    expect(router.currentRoute.value.query.error).toBe('登录暂时不可用，请从创金零售重新进入或稍后重试')
    expect(location.href).not.toContain(syntheticToken); expect(JSON.stringify(history.state)).not.toContain(syntheticToken)
    expect(JSON.stringify([...localWrites.mock.calls, ...sessionWrites.mock.calls])).not.toContain(syntheticToken)
    expect(JSON.stringify(logs.map(spy => spy.mock.calls))).not.toContain(syntheticToken)
    expect(mocks.user.setLogin).not.toHaveBeenCalled()
    router.options.history.destroy()
  })
})

describe('路由对象、重定向链和取消清理', () => {
  const identity = 'userid=synthetic-user&X-Auth-Token=synthetic-host-token&userName=test'
  const token = 'synthetic-host-token'
  function safeRouterState(router: Awaited<typeof import('@/router')>['default'], events: unknown[]) {
    expect(location.href).not.toContain(token)
    expect(JSON.stringify(history.state)).not.toContain(token)
    expect(JSON.stringify(router.currentRoute.value)).not.toContain(token)
    expect(JSON.stringify(events)).not.toContain(token)
  }
  it('初始化入口和后续hash入口均不在currentRoute/afterEach/history保留Token', async () => {
    history.replaceState({}, '', `/h5/random/?${identity}#/report?draftId=3`)
    mocks.channelParameters.mockResolvedValue({ accessToken: 'synthetic-system-jwt', user: { id: 3, isAdmin: false } })
    const { default: router } = await import('@/router')
    const events: unknown[] = []
    router.afterEach((to, from, failure) => events.push({ to, from, failure }))
    await router.push('/report?draftId=3'); safeRouterState(router, events)
    // 模拟宿主以后再次打开一个hash入口，包括已有路由重定向的根路径。
    history.replaceState({ ...history.state, current: `/?${identity}` }, '', `/h5/random/#/?${identity}`)
    await router.push(`/?${identity}`)
    expect(mocks.channelParameters).toHaveBeenCalledTimes(2)
    expect(router.currentRoute.value.path).toBe('/report')
    safeRouterState(router, events)
    expect(router.currentRoute.value.redirectedFrom?.fullPath).toBe('/')
    router.options.history.destroy()
  })
  it('后续跨outer/hash混合入口清理、拒绝且不调用登录API', async () => {
    mocks.user.isLoggedIn = true; mocks.user.userInfo = { id: 1, isAdmin: false }
    const { default: router } = await import('@/router'); await router.push('/mine')
    const events: unknown[] = []; router.afterEach((to, from, failure) => events.push({ to, from, failure }))
    history.replaceState(history.state, '', '/h5/random/?userid=synthetic-user#/report?X-Auth-Token=synthetic-host-token&userName=test')
    await router.push('/report?X-Auth-Token=synthetic-host-token&userName=test')
    expect(router.currentRoute.value.path).toBe('/auth')
    expect(router.currentRoute.value.query.error).toBe('登录入口参数跨位置混合，请从创金零售重新进入')
    expect(mocks.channelParameters).not.toHaveBeenCalled(); expect(mocks.devLogin).not.toHaveBeenCalled()
    safeRouterState(router, events); router.options.history.destroy()
  })
  it('后续入口失败重定向链也没有Token', async () => {
    mocks.user.isLoggedIn = true; mocks.user.userInfo = { id: 1, isAdmin: false }
    const { default: router } = await import('@/router'); await router.push('/mine')
    const events: unknown[] = []; router.afterEach((to, from, failure) => events.push({ to, from, failure }))
    mocks.channelParameters.mockRejectedValue(new Error(`upstream ${token}`))
    await router.push(`/report?${identity}`)
    expect(router.currentRoute.value.path).toBe('/auth')
    expect(router.currentRoute.value.redirectedFrom?.fullPath).toBe('/report')
    safeRouterState(router, events); router.options.history.destroy()
  })
  it('等待交换时取消导航，afterEach失败对象与地址也不残留Token', async () => {
    let finish!: (value: unknown) => void
    let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    mocks.channelParameters.mockImplementation(() => { entered(); return new Promise(resolve => { finish = resolve }) })
    const { default: router } = await import('@/router')
    const events: unknown[] = []; router.afterEach((to, from, failure) => events.push({ to, from, failure }))
    const first = router.push(`/report?${identity}`)
    await started
    await router.push('/auth')
    finish({ accessToken: 'synthetic-system-jwt', user: { id: 3, isAdmin: false } })
    await first
    expect(router.currentRoute.value.path).toBe('/auth')
    expect(mocks.user.setLogin).not.toHaveBeenCalled()
    safeRouterState(router, events); router.options.history.destroy()
  })
})

describe('认证响应不能越过导航generation', () => {
  const parameters = (id: string) => `userid=synthetic-${id}&X-Auth-Token=synthetic-host-${id}&userName=${id}`
  const login = (id: number) => ({ accessToken: `synthetic-system-jwt-${id}`, user: { id, isAdmin: false } })
  it.each(['success', 'failure'])('A/B身份乱序时旧%s不能覆盖或清掉B', async outcome => {
    let finishOld!: (value?: unknown) => void
    let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    mocks.channelParameters.mockImplementationOnce(() => { entered(); return new Promise((resolve, reject) => { finishOld = value => outcome === 'success' ? resolve(value) : reject(new Error('synthetic-old-failure')) }) }).mockResolvedValueOnce(login(2))
    const { default: router } = await import('@/router')
    const first = router.push(`/report?${parameters('A')}`); await started
    await router.push(`/mine?${parameters('B')}`)
    const clears = mocks.user.clear.mock.calls.length
    expect(mocks.user.userInfo?.id).toBe(2)
    finishOld(login(1)); await first
    expect(mocks.user.userInfo?.id).toBe(2); expect(mocks.user.setLogin).toHaveBeenCalledOnce()
    expect(mocks.user.clear).toHaveBeenCalledTimes(clears)
    expect(router.currentRoute.value.path).toBe('/mine')
    expect(JSON.stringify(router.currentRoute.value)).not.toContain('synthetic-host-')
    router.options.history.destroy()
  })
  it.each(['success', 'failure'])('旧me恢复%s不能覆盖或清掉新参数账号', async outcome => {
    mocks.user.isLoggedIn = true; mocks.user.userInfo = null
    let finishOld!: (value?: unknown) => void; let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    mocks.me.mockImplementationOnce(() => { entered(); return new Promise((resolve, reject) => { finishOld = value => outcome === 'success' ? resolve(value) : reject(new Error('synthetic-old-me-failure')) }) })
    mocks.channelParameters.mockResolvedValueOnce(login(2))
    const { default: router } = await import('@/router')
    const first = router.push('/report'); await started
    await router.push(`/mine?${parameters('B')}`)
    const clears = mocks.user.clear.mock.calls.length
    finishOld({ id: 1, isAdmin: true }); await first
    expect(mocks.user.userInfo?.id).toBe(2); expect(mocks.user.setUserInfo).not.toHaveBeenCalled()
    expect(mocks.user.clear).toHaveBeenCalledTimes(clears)
    expect(router.currentRoute.value.path).toBe('/mine'); router.options.history.destroy()
  })
  it.each(['success', 'failure'])('旧ticket请求%s不能覆盖或清掉参数账号', async outcome => {
    let finishOld!: (value?: unknown) => void; let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    mocks.channelSso.mockImplementationOnce(() => { entered(); return new Promise((resolve, reject) => { finishOld = value => outcome === 'success' ? resolve(value) : reject(new Error('synthetic-old-ticket-failure')) }) })
    mocks.channelParameters.mockResolvedValueOnce(login(2))
    const { default: router } = await import('@/router')
    const first = router.push('/report?ticket=synthetic-old-ticket'); await started
    await router.push(`/mine?${parameters('B')}`)
    const clears = mocks.user.clear.mock.calls.length
    finishOld(login(1)); await first
    expect(mocks.user.userInfo?.id).toBe(2); expect(mocks.user.setLogin).toHaveBeenCalledOnce()
    expect(mocks.user.clear).toHaveBeenCalledTimes(clears)
    expect(router.currentRoute.value.path).toBe('/mine'); router.options.history.destroy()
  })
  it('重复跳转当前页面也会取消旧认证，不落旧登录态', async () => {
    const { default: router } = await import('@/router'); await router.push('/auth')
    let finish!: (value: unknown) => void; let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    mocks.channelParameters.mockImplementationOnce(() => { entered(); return new Promise(resolve => { finish = resolve }) })
    const first = router.push(`/report?${parameters('A')}`); await started
    await router.push('/auth')
    finish(login(1)); await first
    expect(mocks.user.setLogin).not.toHaveBeenCalled(); expect(router.currentRoute.value.path).toBe('/auth')
    router.options.history.destroy()
  })
})
