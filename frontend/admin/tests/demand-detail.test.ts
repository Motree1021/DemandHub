// @vitest-environment jsdom
/** 需求详情页布局冒烟：A 区横向表单 / 需求要素表单（置灰、x/27、D9 恒灰）/ 处理进度 tab / 物料需求无要素区。 */
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { beforeAll, describe, expect, it, vi } from 'vitest'

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

const mocks = vi.hoisted(() => ({ detail: vi.fn(), flow: vi.fn() }))
/** 未涉及的 api 对象：任何方法都自动返回空数组（面板 onMounted 拉数用） */
function autoApi() {
  return new Proxy({}, { get: () => vi.fn().mockResolvedValue([]) })
}
vi.mock('@/api', () => ({
  demandApi: { detail: mocks.detail },
  flowApi: { detail: mocks.flow },
  triageApi: autoApi(),
  solutionApi: autoApi(),
  commentApi: autoApi(),
  effortApi: autoApi(),
  relationApi: autoApi(),
  assistApi: autoApi(),
  ragApi: autoApi(),
  authApi: autoApi(),
  usersApi: autoApi(),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import DemandDetail from '../src/views/demand/DemandDetail.vue'
import CommonZoneCard from '../src/views/demand/blocks/CommonZoneCard.vue'
import ElementsCard from '../src/views/demand/blocks/ElementsCard.vue'

const standard = {
  type: 'TECH', name: '科技需求', version: 'v1',
  elements: [
    { key: 'title', label: '需求标题', kind: 'text', zone: 'A', path: 'title' },
    { key: 'requester', label: '提报人', kind: 'text', zone: 'A', path: 'submitterName' },
    { key: 'urgency', label: '紧急程度', kind: 'enum', zone: 'A', path: 'urgency', options: { NORMAL: '普通', URGENT: '紧急' } },
    { key: 'content', label: '原始提报', kind: 'text', zone: 'A', path: 'content' },
    { key: 'businessGoal', label: '业务目标', kind: 'text', zone: 'B', path: 'elements.B.businessGoal' },
    { key: 'userRole', label: '目标用户', kind: 'text', zone: 'C', path: 'elements.C.userRole' },
    { key: 'functionDescription', label: '功能描述', kind: 'text', zone: 'D', path: 'elements.D.functionDescription' },
    { key: 'proposedSolution', label: '建议方案', kind: 'text', zone: 'D', path: 'elements.D.proposedSolution' },
  ],
  commonFields: [], optionalFields: [], subtypeFields: {},
}

function techDemand(ext: Record<string, unknown> = {}) {
  return {
    id: 1, demandNo: 'TECH-20261013-001', title: '持仓报表优化', demandTypeCode: 'TECH',
    urgency: 'NORMAL', status: 'ANALYZING', content: '客户经理要更快看到持仓',
    submitterName: '张三', submitterDept: '机构业务部', revision: 1, fieldSources: {},
    changeLogs: [], ext, elements: { B: { businessGoal: '晨会前出数' }, C: {}, D: { proposedSolution: '复用报表平台' } },
  }
}
const quality = [
  { key: 'title', label: '需求标题', status: 'OK' as const, note: '' },
  { key: 'businessGoal', label: '业务目标', status: 'OK' as const, note: '' },
  { key: 'userRole', label: '目标用户', status: 'MISSING' as const, note: '未填写' },
]

function bundle(demand: Record<string, unknown>, withStandard = true) {
  return { demand, quality, standard: withStandard ? standard : null, messages: [], attachments: [] }
}

function mountDetail() {
  mocks.flow.mockResolvedValue({ transitions: [], availableActions: [] })
  return mount(DemandDetail, { global: { plugins: [ElementPlus, createPinia()] } })
}

describe('需求详情页布局', () => {
  it('科技需求：A 区表单 + 要素表单 + 处理进度 tab 齐备', async () => {
    mocks.detail.mockResolvedValue(bundle(techDemand()))
    const wrapper = mountDetail()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('A · 公共要素')
    expect(text).toContain('需求要素')
    expect(text).toContain('1 项缺失')
    expect(text).toContain('处理进度')
    expect(wrapper.findComponent(CommonZoneCard).exists()).toBe(true)
    expect(wrapper.findComponent(ElementsCard).exists()).toBe(true)
  })

  it('物料需求：不渲染 B/C/D 要素表单', async () => {
    mocks.detail.mockResolvedValue(bundle({ ...techDemand(), demandTypeCode: 'MATL' }, false))
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.findComponent(ElementsCard).exists()).toBe(false)
    expect(wrapper.findComponent(CommonZoneCard).exists()).toBe(true)
  })

  it('判型为功能需求：B/C 区置灰；D9 恒灰且无状态胶囊', async () => {
    mocks.detail.mockResolvedValue(bundle(techDemand({ typeRecognition: { confirmed: 'function' } })))
    const wrapper = mountDetail()
    await flushPromises()
    const card = wrapper.findComponent(ElementsCard)
    expect(card.text()).toContain('需求要素')
    expect(card.text()).toContain('功能需求') // 标题旁层级 tag（与列表同款颜色口径）
    const zones = card.findAll('.zone')
    expect(zones[0].classes()).toContain('gray')  // B
    expect(zones[1].classes()).toContain('gray')  // C
    expect(zones[2].classes()).not.toContain('gray') // D
    const d9 = card.findAll('.zone-row').find(r => r.text().includes('提报人建议方案'))!
    expect(d9.classes()).toContain('gray')
    expect(d9.text()).toContain('选填·不参与评估')
    expect(wrapper.text()).toContain('功能需求') // 判型徽标（confirmed 无 AI 判后缀）
  })

  it('判型为用户需求：仅 B 区置灰；AI 判徽标带后缀', async () => {
    mocks.detail.mockResolvedValue(bundle(techDemand({ typeRecognition: { business: 0.1, user: 0.8, function: 0.1 } })))
    const wrapper = mountDetail()
    await flushPromises()
    const zones = wrapper.findComponent(ElementsCard).findAll('.zone')
    expect(zones[0].classes()).toContain('gray')
    expect(zones[1].classes()).not.toContain('gray')
    expect(wrapper.text()).toContain('用户需求（AI 判）')
  })

  it('公共要素卡：A 区渲染值与枚举文案，无标准时降级简表', async () => {
    const full = mount(CommonZoneCard, {
      props: { demand: techDemand() as never, standard: standard as never, quality },
      global: { plugins: [ElementPlus] },
    })
    expect(full.text()).toContain('持仓报表优化')
    expect(full.text()).toContain('普通') // urgency 枚举转中文
    const fallback = mount(CommonZoneCard, {
      props: { demand: techDemand() as never, standard: null, quality: [] },
      global: { plugins: [ElementPlus] },
    })
    expect(fallback.text()).toContain('张三')
    expect(fallback.text()).toContain('客户经理要更快看到持仓')
  })
})
