import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/report'
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
  }
]

const router = createRouter({
  history: createWebHistory('/h5/'),
  routes
})

router.beforeEach((to, _from, next) => {
  // 创金零售跳转入口：识别 from=chuangjinls，阶段 2 接入静默 OAuth
  document.title = (to.meta.title as string) || 'DemandHub'
  next()
})

export default router
