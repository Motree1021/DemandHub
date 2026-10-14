// @vitest-environment jsdom
/** P4 通知中心：列表渲染 / 点击已读并跳转 / 全部已读 / 偏好开关（TODO 不可关）。 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

beforeAll(() => {
  // jsdom 26 自带 matchMedia 占位（调用返回 undefined），必须无条件覆盖
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {} unobserve() {} disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})

const mocks = vi.hoisted(() => ({
  mine: vi.fn(), unreadCount: vi.fn(), read: vi.fn(), readAll: vi.fn(),
  preferences: vi.fn(), savePreference: vi.fn(), push: vi.fn(),
}))
vi.mock('@/api', () => ({
  notificationApi: {
    mine: mocks.mine,
    unreadCount: mocks.unreadCount,
    read: mocks.read,
    readAll: mocks.readAll,
    preferences: mocks.preferences,
    savePreference: mocks.savePreference,
  },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

import NotificationCenter from '../src/views/notify/NotificationCenter.vue'

const MAIL = {
  id: 1, demandId: 7, templateCode: 'SUBMIT', notifyType: 'TODO',
  title: '新需求待受理：D20261014-001', content: '需求内容摘要', link: '/demands/7',
  isRead: false, readAt: null, createdAt: '2026-10-14 10:00:00',
}

function mountPage() {
  return mount(NotificationCenter, { global: { plugins: [ElementPlus] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.mine.mockResolvedValue({ records: [MAIL], total: 1, size: 10, current: 1, pages: 1 })
  mocks.unreadCount.mockResolvedValue({ count: 1 })
  mocks.read.mockResolvedValue({ updated: 1 })
  mocks.readAll.mockResolvedValue({ updated: 3 })
  mocks.preferences.mockResolvedValue([
    { notifyType: 'TODO', enabled: true, closable: false },
    { notifyType: 'STATUS_CHANGE', enabled: true, closable: true },
  ])
  mocks.savePreference.mockResolvedValue({ success: true })
})

afterEach(() => { document.body.innerHTML = '' })

describe('通知中心', () => {
  it('渲染信件与未读数，点击行标记已读并跳转 link', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('新需求待受理：D20261014-001')
    expect(wrapper.text()).toContain('全部已读（1）')
    await wrapper.find('tbody tr').trigger('click')
    await flushPromises()
    expect(mocks.read).toHaveBeenCalledWith(1)
    expect(mocks.push).toHaveBeenCalledWith('/demands/7')
  })

  it('全部已读后重新加载', async () => {
    const wrapper = mountPage()
    await flushPromises()
    const button = wrapper.findAll('button').find(b => b.text().includes('全部已读'))!
    await button.trigger('click')
    await flushPromises()
    expect(mocks.readAll).toHaveBeenCalled()
    expect(mocks.mine).toHaveBeenCalledTimes(2)
  })

  it('偏好抽屉：TODO 开关禁用，切换其他类型保存', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '偏好设置')!.trigger('click')
    await flushPromises()
    // el-drawer 默认渲染在组件树内（不 append-to-body）
    const drawer = wrapper.find('.el-drawer')
    expect(drawer.text()).toContain('待办提醒')
    const switches = wrapper.findAll('.el-drawer .el-switch')
    expect(switches[0].classes()).toContain('is-disabled')  // TODO 不可关
    await switches[1].find('input').trigger('click')
    await flushPromises()
    expect(mocks.savePreference).toHaveBeenCalledWith('STATUS_CHANGE', false)
  })
})
