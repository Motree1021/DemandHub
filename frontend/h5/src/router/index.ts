import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'
import { channelSso, me } from '@/api/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/report'
  },
  {
    path: '/auth',
    name: 'Auth',
    component: () => import('@/views/auth/index.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/report',
    name: 'Report',
    component: () => import('@/views/report/index.vue'),
    meta: { title: '需求提报' }
  },
  {
    path: '/mine',
    name: 'Mine',
    component: () => import('@/views/mine/index.vue'),
    meta: { title: '我的需求' }
  },
  {
    path: '/notification',
    name: 'Notification',
    component: () => import('@/views/notification/index.vue'),
    meta: { title: '通知' }
  },
  {
    path: '/demand/:id',
    name: 'DemandDetail',
    component: () => import('@/views/demand/detail.vue'),
    meta: { title: '需求详情' }
  },
  {
    path: '/demand/:id/acceptance',
    name: 'Acceptance',
    component: () => import('@/views/demand/acceptance.vue'),
    meta: { title: '验收评价' }
  },
  {
    path: '/triage',
    name: 'Triage',
    component: () => import('@/views/triage/index.vue'),
    meta: { title: '待受理队列' }
  }
]

const router = createRouter({
  history: createWebHistory('/h5/'),
  routes
})

/**
 * 路由守卫（对接标准 v2.1 §3.1，P5 任务 5.1）：
 * 1. 识别 URL ticket（from 仅决定渠道适配与嵌入外壳）→ 调 channel-sso（渠道码后端白名单选定）
 *    → 存 token → replace 清除地址栏 ticket/from/state；
 *    URL 明文 userid/name 等身份字段一律不读、不采信（身份仅经服务端 verify 响应返回）。
 * 2. 票据校验失败 → /auth 错误页（复用后端 AC07 文案）。
 * 3. 无 ticket 且无登录态 → /auth 提示页（非企微 UA 引导从创金零售进入）。
 */
router.beforeEach(async (to, _from, next) => {
  document.title = (to.meta.title as string) || 'DemandHub'

  const userStore = useUserStore()

  const from = to.query.from as string | undefined
  if (from) {
    userStore.setFrom(from)
  }

  // 一次性票据登录：任何路由携带 ticket 都先完成登录再进入目标页
  const ticket = to.query.ticket as string | undefined
  if (ticket) {
    try {
      const resp = await channelSso(
        userStore.from || 'chuangjinls',
        ticket,
        to.query.state as string | undefined
      )
      userStore.setLogin(resp)
      // 登录成功后立即从地址栏清除 ticket/from/state（§3.2），避免刷新重复消费与票据泄露
      const query = { ...to.query }
      delete query.ticket
      delete query.from
      delete query.state
      return next({ path: to.path, query, replace: true })
    } catch (e) {
      const message = e instanceof Error && e.message ? e.message : '登录失败，请从创金零售重新进入'
      return next({ path: '/auth', query: { error: message }, replace: true })
    }
  }

  if (to.meta.public) {
    return next()
  }

  if (!userStore.isLoggedIn) {
    return next({ path: '/auth', query: { redirect: to.fullPath } })
  }

  // token 有效但用户信息丢失（浏览器刷新场景）：恢复用户信息
  if (!userStore.userInfo) {
    try {
      userStore.setUserInfo(await me())
    } catch {
      // 401 由响应拦截器统一处理（刷新 token 或重登）
    }
  }

  next()
})

export default router
