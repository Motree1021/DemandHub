import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录' }
  },
  {
    path: '/',
    component: () => import('@/layout/index.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/index.vue'),
        meta: { title: '工作台' }
      },
      {
        path: 'demand/report',
        name: 'DemandReport',
        component: () => import('@/views/placeholder/index.vue'),
        meta: { title: '需求提报' }
      },
      {
        path: 'demand/list',
        name: 'DemandList',
        component: () => import('@/views/placeholder/index.vue'),
        meta: { title: '需求列表' }
      },
      {
        path: 'notification',
        name: 'Notification',
        component: () => import('@/views/placeholder/index.vue'),
        meta: { title: '通知中心' }
      },
      {
        path: 'system',
        name: 'System',
        component: () => import('@/views/placeholder/index.vue'),
        meta: { title: '系统管理' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：未登录跳登录页（阶段 2 接入真实认证，当前放行）
router.beforeEach((to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - DemandHub` : 'DemandHub 需求管理系统'
  next()
})

export default router
