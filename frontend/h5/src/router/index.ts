import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/user'
import { silentLogin, me } from '@/api/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/report'
  },
  {
    path: '/auth',
    name: 'Auth',
    component: () => import('@/views/auth/index.vue'),
    meta: { title: '登录授权', public: true }
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
 * 路由守卫：
 * 1. 识别 from=chuangjinls（创金零售 App 跳转入口），记录来源
 * 2. URL 携带 code（企微静默授权回调）时先完成登录再进入目标页
 * 3. 无登录态时进入 /auth 授权页（一期 Mock；二期直接重定向企微 OAuth 链接）
 */
router.beforeEach(async (to, _from, next) => {
  document.title = (to.meta.title as string) || 'DemandHub'

  const userStore = useUserStore()

  const from = to.query.from as string | undefined
  if (from) {
    userStore.setFrom(from)
  }

  // 企微静默授权回调：code 换 token 后继续访问（去掉地址栏 code，避免刷新重复登录）
  const code = to.query.code as string | undefined
  if (code && !to.meta.public) {
    try {
      const resp = await silentLogin(code, userStore.from || undefined)
      userStore.setLogin(resp)
      const query = { ...to.query }
      delete query.code
      return next({ path: to.path, query, replace: true })
    } catch {
      return next({ path: '/auth', query: { redirect: to.fullPath } })
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
