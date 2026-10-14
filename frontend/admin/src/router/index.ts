import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { getAccessToken } from '@/api/request'

const router = createRouter({
  // hash 路由：FastAPI 静态托管 /admin 下刷新/直达不失效，无需服务端 rewrite 规则
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/Login.vue'), meta: { public: true } },
    {
      path: '/change-password', name: 'change-password',
      component: () => import('@/views/ChangePassword.vue'),
    },
    {
      path: '/',
      component: () => import('@/layout/MainLayout.vue'),
      children: [
        // 首页落点选「我的处理」：两种角色都可访问，避免 HANDLER 被守卫弹回 '/' 形成重定向循环
        { path: '', redirect: '/my-tasks' },
        {
          path: 'my-tasks', name: 'my-tasks',
          component: () => import('@/views/demand/MyTasks.vue'),
          meta: { title: '我的处理' },
        },
        {
          path: 'triage', name: 'triage',
          component: () => import('@/views/demand/TriageWorkbench.vue'),
          // P4 角色放开：受理族=经理/管理者（后端 require_role 同源，ADMIN 直通）
          meta: { roles: ['ADMIN', 'MANAGER', 'EXECUTIVE'], title: '受理分派' },
        },
        {
          path: 'demands', name: 'demands',
          component: () => import('@/views/demand/DemandList.vue'),
          meta: { title: '需求列表' },
        },
        {
          path: 'demands/:id', name: 'demand-detail',
          component: () => import('@/views/demand/DemandDetail.vue'),
          meta: { title: '需求详情' },
        },
        {
          path: 'notifications', name: 'notifications',
          component: () => import('@/views/notify/NotificationCenter.vue'),
          meta: { title: '通知中心' },
        },
        {
          path: 'board/manager', name: 'board-manager',
          component: () => import('@/views/board/BoardManager.vue'),
          meta: { roles: ['ADMIN', 'EXECUTIVE', 'MANAGER'], title: '经营看板' },
        },
        {
          path: 'board/org', name: 'board-org',
          component: () => import('@/views/board/BoardOrg.vue'),
          meta: { roles: ['ADMIN', 'EXECUTIVE', 'MANAGER'], title: '组织看板' },
        },
        {
          path: 'report', name: 'report',
          component: () => import('@/views/report/ReportTasks.vue'),
          meta: { roles: ['ADMIN', 'EXECUTIVE', 'MANAGER'], title: '报表导出' },
        },
        {
          path: 'users', name: 'users',
          component: () => import('@/views/Users.vue'),
          meta: { roles: ['ADMIN'], title: '用户管理' },
        },
        {
          path: 'notify-templates', name: 'notify-templates',
          component: () => import('@/views/admin/NotifyTemplates.vue'),
          meta: { roles: ['ADMIN'], title: '通知模板' },
        },
        {
          path: 'sys-dicts', name: 'sys-dicts',
          component: () => import('@/views/admin/SysDicts.vue'),
          meta: { roles: ['ADMIN'], title: '字典管理' },
        },
        {
          path: 'demand-types', name: 'demand-types',
          component: () => import('@/views/admin/DemandTypes.vue'),
          meta: { roles: ['ADMIN'], title: '类型管理' },
        },
        {
          path: 'state-machines', name: 'state-machines',
          component: () => import('@/views/admin/StateMachines.vue'),
          meta: { roles: ['ADMIN'], title: '状态机管理' },
        },
        {
          path: 'sla-configs', name: 'sla-configs',
          component: () => import('@/views/admin/SlaConfigs.vue'),
          meta: { roles: ['ADMIN'], title: 'SLA 配置' },
        },
        {
          path: 'channels', name: 'channels',
          component: () => import('@/views/admin/Channels.vue'),
          meta: { roles: ['ADMIN'], title: '渠道管理' },
        },
        {
          path: 'orgs', name: 'orgs',
          component: () => import('@/views/admin/Orgs.vue'),
          meta: { roles: ['ADMIN'], title: '组织管理' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

/** 页面级守卫：未登录→/login；强制改密→/change-password；角色不符→提示回首页。 */
export function guard(to: { path: string; meta: Record<string, unknown> }, auth: ReturnType<typeof useAuthStore>) {
  if (to.meta.public) return true
  if (!getAccessToken()) return { path: '/login', query: { redirect: to.path } }
  if (auth.mustChangePwd && to.path !== '/change-password') return { path: '/change-password' }
  const roles = to.meta.roles as string[] | undefined
  if (roles?.length && (!auth.role || !roles.includes(auth.role))) return { path: '/' }
  return true
}

router.beforeEach(async to => {
  const auth = useAuthStore()
  if (getAccessToken() && !auth.user) await auth.fetchMe().catch(() => undefined)
  return guard(to, auth)
})

export default router
