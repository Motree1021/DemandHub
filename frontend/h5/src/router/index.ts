import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/store/user'
import { channelSso, me } from '@/api/auth'
import { cleanTicketUrl, readTicketEntry } from '@/utils/auth-entry'

// hash history 初始化之前捕获宿主外层 ticket；认证后同时清理外层与 hash 参数。
let initialEntry = readTicketEntry(new URL(window.location.href))
const router = createRouter({ history: createWebHashHistory(), routes: [
  { path: '/', redirect: '/report' },
  { path: '/auth', component: () => import('@/views/auth/index.vue'), meta: { title: '登录', public: true } },
  { path: '/report', component: () => import('@/views/report/index.vue'), meta: { title: '需求提报' } },
  { path: '/mine', component: () => import('@/views/mine/index.vue'), meta: { title: '我的需求' } },
  { path: '/demand/:id', component: () => import('@/views/demand/detail.vue'), meta: { title: '需求详情' } },
  { path: '/admin', component: () => import('@/views/admin/index.vue'), meta: { title: '需求整理', admin: true } },
  { path: '/:pathMatch(.*)*', redirect: '/report' }
] })
router.beforeEach(async to => {
  document.title = String(to.meta.title || 'DemandHub')
  const user = useUserStore()
  const entry = initialEntry || readTicketEntry(new URL(window.location.href))
  initialEntry = null
  if (entry) {
    user.setFrom(entry.from)
    try {
      user.setLogin(await channelSso(entry.from, entry.ticket, entry.state))
    } catch (error) {
      user.clear()
      history.replaceState(history.state, '', cleanTicketUrl(new URL(window.location.href)))
      return { path: '/auth', query: { error: error instanceof Error ? error.message : '请从创金零售重新进入' }, replace: true }
    }
    history.replaceState(history.state, '', cleanTicketUrl(new URL(window.location.href)))
    const query = { ...to.query }
    ;['ticket', 'from', 'state'].forEach(key => delete query[key])
    return { path: to.path, query, replace: true }
  }
  if (to.meta.public) return true
  if (!user.isLoggedIn) return { path: '/auth', query: { redirect: to.fullPath }, replace: true }
  if (!user.userInfo) {
    try { user.setUserInfo(await me()) } catch { user.clear(); return { path: '/auth', query: { error: '登录已过期，请从创金零售重新进入' }, replace: true } }
  }
  if (to.meta.admin && !user.userInfo?.isAdmin) return '/mine'
  return true
})
export default router
