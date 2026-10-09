import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Vant from 'vant'
import AuthView from '@/views/auth/index.vue'
import { testLogin } from '@/api/auth'

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/api/request', () => ({ get: mocks.get, post: mocks.post, TOKEN_KEY: 'demandhub_h5_token' }))
const route = { query: {} as Record<string, unknown> }
const router = { replace: vi.fn() }
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => router }))

function mountAuth() {
  return mount(AuthView, { global: { plugins: [Vant] } })
}

beforeEach(() => { vi.clearAllMocks(); vi.unstubAllEnvs(); setActivePinia(createPinia()); route.query = {} })

describe('测试环境手动登录', () => {
  it('testLogin 调用 /auth/test-login，camelCase 请求体', async () => {
    mocks.post.mockResolvedValue({ accessToken: 'jwt', tokenType: 'Bearer', expiresIn: 28800, user: { id: 1 } })
    await testLogin('测试用户', 'tester-001')
    expect(mocks.post).toHaveBeenCalledWith('/auth/test-login', { name: '测试用户', wecomUserid: 'tester-001' })
  })
  it('VITE_TEST_LOGIN_ENTRY=true 时展示测试登录入口并走 test-login', async () => {
    vi.stubEnv('VITE_TEST_LOGIN_ENTRY', 'true')
    mocks.post.mockResolvedValue({ accessToken: 'jwt', tokenType: 'Bearer', expiresIn: 28800, user: { id: 1 } })
    const wrapper = mountAuth()
    expect(wrapper.text()).toContain('测试环境登录')
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('测试用户')
    await inputs[1].setValue('tester-001')
    const buttons = wrapper.findAll('button')
    await buttons[buttons.length - 1].trigger('click')
    await flushPromises()
    expect(mocks.post).toHaveBeenCalledWith('/auth/test-login', { name: '测试用户', wecomUserid: 'tester-001' })
    expect(mocks.post).not.toHaveBeenCalledWith('/auth/dev-login', expect.anything())
    expect(router.replace).toHaveBeenCalledWith('/report')
  })
  it('未设置入口变量时保持开发登录语义', () => {
    const wrapper = mountAuth()
    expect(wrapper.text()).toContain('开发环境登录')
  })
})
