import { createRouter, createWebHashHistory, isNavigationFailure, NavigationFailureType, type RouteLocation } from 'vue-router'
import { useUserStore } from '@/store/user'
import { channelParameters, channelSso, me } from '@/api/auth'
import { CHANNEL_ENTRY_KEYS, cleanChannelHistoryState, cleanChannelQuery, cleanChannelUrl, readChannelEntry } from '@/utils/auth-entry'

// 路由初始化前捕获一次性入口，立即清URL和旧history状态；失败也不回填宿主token。
const startupUrl = new URL(window.location.href)
let initialEntry = readChannelEntry(startupUrl)
const cleanedStartupUrl = cleanChannelUrl(startupUrl)
if (cleanedStartupUrl !== window.location.pathname + window.location.search + window.location.hash) {
  history.replaceState(null, '', cleanedStartupUrl)
}
function entryError(error: unknown, parameters: boolean): string {
  const code = error && typeof error === 'object' && 'code' in error ? error.code : undefined
  if (parameters && code === 404) return '参数联调登录尚未开启'
  if (code === 1107) return '登录已失效，请从创金零售重新进入'
  if (code === 1113) return '账号不可用，请联系管理员'
  if (code === 1108) return '该渠道已停用，请联系管理员'
  // 后端任意message不得进入路由；即使错误原文带宿主token也不会再次泄露。
  return '登录暂时不可用，请从创金零售重新进入或稍后重试'
}
const router = createRouter({ history: createWebHashHistory(), routes: [
  { path: '/', redirect: '/report' },
  { path: '/auth', component: () => import('@/views/auth/index.vue'), meta: { title: '登录', public: true } },
  { path: '/report', component: () => import('@/views/report/index.vue'), meta: { title: '需求提报' } },
  { path: '/mine', component: () => import('@/views/mine/index.vue'), meta: { title: '我的需求' } },
  { path: '/demand/:id', component: () => import('@/views/demand/detail.vue'), meta: { title: '需求详情' } },
  { path: '/admin', component: () => import('@/views/admin/index.vue'), meta: { title: '需求整理', admin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/report' }
] })
function scrubRouteEntry(location: RouteLocation, seen = new Set<RouteLocation>()) {
  if (seen.has(location)) return
  seen.add(location)
  const safe = router.resolve({ path: location.path, query: cleanChannelQuery(location.query), hash: location.hash })
  location.query = safe.query
  location.fullPath = safe.fullPath
  if ('href' in location) (location as RouteLocation & { href: string }).href = safe.href
  if (location.redirectedFrom) scrubRouteEntry(location.redirectedFrom, seen)
}
let navigationGeneration = 0
router.afterEach((_to, _from, failure) => {
  // 重复跳转不会执行beforeEach，但同样会取消正在等待的旧导航。
  if (isNavigationFailure(failure, NavigationFailureType.duplicated)) navigationGeneration++
})
router.beforeEach(async to => {
  const generation = ++navigationGeneration
  document.title = String(to.meta.title || 'DemandHub')
  const user = useUserStore()
  const routeUrl = new URL(window.location.href)
  routeUrl.hash = to.fullPath
  const entry = initialEntry || readChannelEntry(routeUrl)
  initialEntry = null
  const hasEntryQuery = CHANNEL_ENTRY_KEYS.some(key => Object.prototype.hasOwnProperty.call(to.query, key))
  // Vue Router会把guard重定向源保留在redirectedFrom；先原地清理整条链再做任何异步工作。
  scrubRouteEntry(to)
  if (entry || hasEntryQuery) {
    // 兼容后续hash入口；任何网络请求开始前也先清实际地址栏。
    const currentUrl = new URL(window.location.href)
    const cleanedUrl = cleanChannelUrl(currentUrl)
    if (cleanedUrl !== window.location.pathname + window.location.search + window.location.hash) history.replaceState(cleanChannelHistoryState(history.state), '', cleanedUrl)
    if (entry?.kind === 'invalid') {
      user.clear()
      return { path: '/auth', query: { error: entry.message }, replace: true }
    }
    if (entry) {
      try {
        // 交换入口身份时先清旧JWT；失败不能沿用上个账号。
        user.clear()
        if (entry.kind === 'parameters') {
          user.setFrom('chuangjinls')
          const login = await channelParameters(entry.parameters)
          if (generation !== navigationGeneration) return false
          user.setLogin(login)
        } else {
          user.setFrom(entry.parameters.from)
          const login = await channelSso(entry.parameters.from, entry.parameters.ticket, entry.parameters.state)
          if (generation !== navigationGeneration) return false
          user.setLogin(login)
        }
      } catch (error) {
        if (generation !== navigationGeneration) return false
        user.clear()
        return { path: '/auth', query: { error: entryError(error, entry.kind === 'parameters') }, replace: true }
      }
    }
  }
  if (to.meta.public) return true
  if (!user.isLoggedIn) return { path: '/auth', query: { redirect: to.fullPath }, replace: true }
  if (!user.userInfo) {
    try {
      const info = await me()
      if (generation !== navigationGeneration) return false
      user.setUserInfo(info)
    } catch {
      if (generation !== navigationGeneration) return false
      user.clear()
      return { path: '/auth', query: { error: '登录已过期，请从创金零售重新进入' }, replace: true }
    }
  }
  if (to.meta.admin && !user.userInfo?.isAdmin) return '/mine'
  return true
})
export default router
