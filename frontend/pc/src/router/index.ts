import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/store/modules/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/login/index.vue'),
    meta: { title: '登录', public: true }
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
        component: () => import('@/views/demand/report.vue'),
        meta: { title: '需求提报' }
      },
      {
        path: 'demand/list',
        name: 'DemandList',
        component: () => import('@/views/demand/list.vue'),
        meta: { title: '需求列表' }
      },
      {
        path: 'demand/detail/:id',
        name: 'DemandDetail',
        component: () => import('@/views/demand/detail.vue'),
        meta: { title: '需求详情' }
      },
      {
        path: 'board',
        name: 'Board',
        component: () => import('@/views/board/index.vue'),
        meta: { title: '经营看板', roles: ['EXECUTIVE', 'DEMAND_MANAGER'] }
      },
      {
        path: 'workbench/manager',
        name: 'ManagerWorkbench',
        component: () => import('@/views/workbench/manager.vue'),
        meta: { title: '经理工作台', roles: ['DEMAND_MANAGER', 'EXECUTIVE', 'ADMIN'] }
      },
      {
        path: 'workbench/handler',
        name: 'HandlerWorkbench',
        component: () => import('@/views/workbench/handler.vue'),
        meta: { title: '处理人工作台', roles: ['HANDLER'] }
      },
      {
        path: 'notification',
        name: 'Notification',
        component: () => import('@/views/notification/index.vue'),
        meta: { title: '通知中心' }
      },
      {
        path: 'system/grant',
        name: 'RoleGrant',
        component: () => import('@/views/system/grant.vue'),
        meta: { title: '角色授权管理', roles: ['ADMIN'] }
      },
      {
        path: 'system/types',
        name: 'DemandTypes',
        component: () => import('@/views/system/types.vue'),
        meta: { title: '需求类型字典', roles: ['ADMIN'] }
      },
      {
        path: 'system/state-machines',
        name: 'StateMachines',
        component: () => import('@/views/system/state-machines.vue'),
        meta: { title: '状态机配置', roles: ['ADMIN'] }
      },
      {
        path: 'system/templates',
        name: 'NotifyTemplates',
        component: () => import('@/views/system/templates.vue'),
        meta: { title: '通知模板', roles: ['ADMIN'] }
      },
      {
        path: 'system/dicts',
        name: 'SysDicts',
        component: () => import('@/views/system/dicts.vue'),
        meta: { title: '通用字典', roles: ['ADMIN'] }
      },
      {
        path: 'system/sla',
        name: 'SlaConfigs',
        component: () => import('@/views/system/sla.vue'),
        meta: { title: 'SLA 配置', roles: ['ADMIN'] }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：未登录跳登录页；有角色要求的页面校验权限；已登录访问登录页则回首页
router.beforeEach(async (to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - DemandHub` : 'DemandHub 需求管理系统'

  const userStore = useUserStore()

  if (to.meta.public) {
    // 企微回调（/login?code=xxx）即使是已登录态也放行，由登录页完成换账号登录
    if (userStore.isLoggedIn && to.path === '/login' && !to.query.code) {
      return next('/')
    }
    return next()
  }

  if (!userStore.isLoggedIn) {
    return next({ path: '/login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} })
  }

  // 页面刷新后恢复用户信息（含角色），用于菜单与页面级鉴权
  if (!userStore.userInfo) {
    try {
      await userStore.fetchMe()
    } catch {
      // fetchMe 失败时 request 拦截器已处理 401 跳转
      return next(false)
    }
  }

  const needRoles = to.meta.roles as string[] | undefined
  if (needRoles && !needRoles.some((r) => userStore.roles.includes(r))) {
    return next('/dashboard')
  }

  next()
})

export default router
