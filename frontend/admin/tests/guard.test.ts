import { beforeEach, describe, expect, it } from 'vitest'
import { guard } from '@/router'
import { saveTokens, clearTokens } from '@/api/request'

// 路由守卫纯逻辑：不依赖组件渲染，直接断言跳转决策
function fakeAuth(over: Partial<{ user: unknown; mustChangePwd: boolean; role: string | null; roles: string[] }> = {}) {
  const base = { user: null, mustChangePwd: false, role: null, ...over }
  // 与 store getter 同口径：roles 缺省退化为仅主角色
  return { ...base, roles: over.roles ?? (base.role ? [base.role] : []) } as never
}

describe('路由守卫', () => {
  beforeEach(() => clearTokens())

  it('未登录访问受限页跳登录并带 redirect', () => {
    expect(guard({ path: '/users', meta: {} }, fakeAuth())).toEqual({ path: '/login', query: { redirect: '/users' } })
  })

  it('登录页公开放行', () => {
    expect(guard({ path: '/login', meta: { public: true } }, fakeAuth())).toBe(true)
  })

  it('mustChangePwd 时强制跳改密页，改密页自身放行', () => {
    saveTokens('a', 'r')
    const auth = fakeAuth({ mustChangePwd: true, role: 'ADMIN' })
    expect(guard({ path: '/users', meta: { roles: ['ADMIN'] } }, auth)).toEqual({ path: '/change-password' })
    expect(guard({ path: '/change-password', meta: {} }, auth)).toBe(true)
  })

  it('角色不符拒绝回首页，角色匹配放行', () => {
    saveTokens('a', 'r')
    const handler = fakeAuth({ role: 'HANDLER' })
    expect(guard({ path: '/users', meta: { roles: ['ADMIN'] } }, handler)).toEqual({ path: '/' })
    const admin = fakeAuth({ role: 'ADMIN' })
    expect(guard({ path: '/users', meta: { roles: ['ADMIN'] } }, admin)).toBe(true)
  })

  // P4：看板/报表=经理族（ADMIN/EXECUTIVE/MANAGER），受理分派同族；通知模板仅 ADMIN
  it('P4 路由角色：看板 HANDLER 弹回、MANAGER 放行；模板仅 ADMIN', () => {
    saveTokens('a', 'r')
    const boardMeta = { roles: ['ADMIN', 'EXECUTIVE', 'MANAGER'] }
    expect(guard({ path: '/board/manager', meta: boardMeta }, fakeAuth({ role: 'HANDLER' })))
      .toEqual({ path: '/' })
    expect(guard({ path: '/board/manager', meta: boardMeta }, fakeAuth({ role: 'MANAGER' }))).toBe(true)
    expect(guard({ path: '/report', meta: boardMeta }, fakeAuth({ role: 'EXECUTIVE' }))).toBe(true)
    expect(guard({ path: '/triage', meta: boardMeta }, fakeAuth({ role: 'MANAGER' }))).toBe(true)
    expect(guard({ path: '/notify-templates', meta: { roles: ['ADMIN'] } },
      fakeAuth({ role: 'EXECUTIVE' }))).toEqual({ path: '/' })
  })

  // 多角色：任一有效角色命中即放行（提报人兼任经理可看板；纯提报人弹回）
  it('多角色：兼任角色命中放行，纯提报人弹回', () => {
    saveTokens('a', 'r')
    const boardMeta = { roles: ['ADMIN', 'EXECUTIVE', 'MANAGER'] }
    expect(guard({ path: '/board/manager', meta: boardMeta },
      fakeAuth({ role: 'REPORTER', roles: ['MANAGER', 'REPORTER'] }))).toBe(true)
    expect(guard({ path: '/board/manager', meta: boardMeta },
      fakeAuth({ role: 'REPORTER', roles: ['REPORTER'] }))).toEqual({ path: '/' })
    expect(guard({ path: '/users', meta: { roles: ['ADMIN'] } },
      fakeAuth({ role: 'REPORTER', roles: ['REPORTER', 'HANDLER'] }))).toEqual({ path: '/' })
  })
})
