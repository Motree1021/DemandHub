// @vitest-environment jsdom
/** P3 AI 辅助面板冒烟：相似需求渲染与跳转 / 空态 / 草稿列表 / 编辑确认入库预填与提交 / 废弃确认。 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'

// matchMedia/ResizeObserver 桩：Element Plus 组件在 jsdom 下需要
beforeAll(() => {
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false, media: query, onchange: null,
      addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
  }
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {} unobserve() {} disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})

const mocks = vi.hoisted(() => ({
  openSession: vi.fn(), generateQuestions: vi.fn(), generateSolution: vi.fn(),
  drafts: vi.fn(), confirm: vi.fn(), discard: vi.fn(), similar: vi.fn(), push: vi.fn(),
}))
vi.mock('@/api', () => ({
  assistApi: {
    openSession: mocks.openSession,
    generateQuestions: mocks.generateQuestions,
    generateSolution: mocks.generateSolution,
    drafts: mocks.drafts,
    confirm: mocks.confirm,
    discard: mocks.discard,
  },
  ragApi: { similar: mocks.similar },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

import AssistPanel from '../src/views/demand/panels/AssistPanel.vue'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const demand: any = { id: 7, status: 'ANALYZING', expectDeliveryAt: '2026-11-01' }

function mountPanel() {
  return mount(AssistPanel, { props: { demand }, global: { plugins: [ElementPlus] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.openSession.mockResolvedValue({ id: 55, scene: 'HANDLE_ASSIST', demandId: 7 })
  mocks.drafts.mockResolvedValue([])
  mocks.similar.mockResolvedValue([])
  mocks.confirm.mockResolvedValue({})
  mocks.discard.mockResolvedValue({ success: true })
})

afterEach(() => {
  document.body.innerHTML = '' // el-dialog teleport 到 body，用例间清理
})

describe('相似需求', () => {
  it('渲染相似度并支持点击跳转详情', async () => {
    mocks.similar.mockResolvedValue([
      { demandId: 9, demandNo: 'DH20260001', title: '历史持仓报表', demandTypeCode: 'TECH', score: 0.86 },
    ])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('DH20260001')
    expect(wrapper.text()).toContain('历史持仓报表')
    expect(wrapper.text()).toContain('86%')
    await wrapper.find('.similar-item').trigger('click')
    expect(mocks.push).toHaveBeenCalledWith({ name: 'demand-detail', params: { id: 9 } })
  })

  it('无相似结果与无草稿时展示空态', async () => {
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('暂无相似历史需求')
    expect(wrapper.text()).toContain('暂无草稿')
  })
})

describe('草稿区', () => {
  it('问题清单草稿逐条渲染，且无确认入库入口', async () => {
    mocks.drafts.mockResolvedValue([
      { id: 1, demandId: 7, sessionId: 55, draftType: 'QUESTIONS', status: 'PENDING',
        content: ['核心使用角色与频次？', '数据来源确认人？'], createdAt: '2026-10-14 10:00:00' },
    ])
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.text()).toContain('核心使用角色与频次？')
    expect(wrapper.text()).toContain('数据来源确认人？')
    expect(wrapper.text()).toContain('AI 生成，待人工确认')
    expect(wrapper.text()).not.toContain('编辑并确认入库')
  })

  it('方案草稿确认：对话框预填 AI 原文，提交带原计划交付日', async () => {
    mocks.drafts.mockResolvedValue([
      { id: 2, demandId: 7, sessionId: 55, draftType: 'SOLUTION', status: 'PENDING',
        content: { specContent: 'AI 理解', solutionContent: 'AI 方案' }, createdAt: '2026-10-14 10:00:00' },
    ])
    const wrapper = mountPanel()
    await flushPromises()
    const openBtn = wrapper.findAll('button').find(b => b.text().includes('编辑并确认入库'))
    expect(openBtn).toBeTruthy()
    await openBtn!.trigger('click')
    await flushPromises()
    // 对话框预填草稿原文（el-dialog 默认不 append-to-body，渲染在组件树内）
    const textareas = wrapper.findAll('textarea')
    expect((textareas[0].element as HTMLTextAreaElement).value).toBe('AI 理解')
    expect((textareas[1].element as HTMLTextAreaElement).value).toBe('AI 方案')
    const okBtn = wrapper.findAll('button').find(b => b.text().trim() === '确认入库')
    expect(okBtn).toBeTruthy()
    await okBtn!.trigger('click')
    await flushPromises()
    expect(mocks.confirm).toHaveBeenCalledWith(2, {
      specContent: 'AI 理解', solutionContent: 'AI 方案', planDeliveryAt: '2026-11-01',
    })
  })

  it('废弃草稿需二次确认', async () => {
    mocks.drafts.mockResolvedValue([
      { id: 3, demandId: 7, sessionId: 55, draftType: 'QUESTIONS', status: 'PENDING',
        content: ['问题一？'], createdAt: '2026-10-14 10:00:00' },
    ])
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue({} as never)
    const wrapper = mountPanel()
    await flushPromises()
    const btn = wrapper.findAll('button').find(b => b.text().includes('废弃'))
    await btn!.trigger('click')
    await flushPromises()
    expect(mocks.discard).toHaveBeenCalledWith(3)
  })
})

describe('生成动作', () => {
  it('首次生成先开需求级共享会话，再调生成接口', async () => {
    mocks.generateQuestions.mockResolvedValue({ id: 4 })
    const wrapper = mountPanel()
    await flushPromises()
    const btn = wrapper.findAll('button').find(b => b.text().includes('生成调研问题清单'))
    await btn!.trigger('click')
    await flushPromises()
    expect(mocks.openSession).toHaveBeenCalledWith(7)
    expect(mocks.generateQuestions).toHaveBeenCalledWith(55)
    expect(mocks.drafts).toHaveBeenCalledTimes(2) // 初次加载 + 生成后刷新
  })
})
