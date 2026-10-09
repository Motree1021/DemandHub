// @vitest-environment jsdom
import { mount, flushPromises, VueWrapper } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import Vant from 'vant'
import Detail from '@/views/demand/detail.vue'
import { newForm } from '@/utils/form'
import type { AgentMessage, DemandEntity, Standard } from '@/api/demand'

const mocks = vi.hoisted(() => ({ getDemand: vi.fn(), closeDemand: vi.fn(), downloadMarkdown: vi.fn(), push: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '1' } }), useRouter: () => ({ push: mocks.push }) }))
vi.mock('@/store/user', () => ({ useUserStore: () => ({ userInfo: { id: 1, name: '管理员', dept: '机构业务部', channelType: 'SSO', isAdmin: false }, ticket: 't', loaded: true }) }))
vi.mock('@/api/demand', () => ({ getDemand: mocks.getDemand, closeDemand: mocks.closeDemand, downloadMarkdown: mocks.downloadMarkdown }))

const QualityListStub = defineComponent({ template: '<div data-quality />' })

function entity(over: Partial<DemandEntity> = {}): DemandEntity {
  return {
    ...newForm(), id: 1, demandNo: 'TECH-20261008-001', subtypeCode: 'SYS_DEV', revision: 3, status: 'DRAFT',
    title: '海报生成智能体', content: '我要做个海报生成智能体，给市场部用',
    submitterId: 1, submitterName: '管理员', submitterDept: '机构业务部', channel: 'H5', sessionId: 11,
    submittedAt: null, closedAt: null, closeReason: null, createdAt: '2026-10-08T09:30:00', updatedAt: '2026-10-08T09:35:00',
    quality: [], changeLogs: [], ...over
  }
}
function message(id: number, role: AgentMessage['role'], content: string, createdAt: string): AgentMessage {
  return { id, sessionId: 11, role, content, structuredPayload: null, createdAt }
}
function changeLog(id: number, source: string, fieldKey: string, oldValue: string, newValue: string) {
  return { id, demandId: 1, fieldKey, oldValue, newValue, source, operatorId: 1, operatorName: '管理员', createdAt: '2026-10-08T09:32:00' }
}

describe('demand detail 提报人补充原话（方案乙）', () => {
  beforeEach(() => vi.clearAllMocks())
  function createWrapper(): VueWrapper {
    return mount(Detail, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, QualityList: QualityListStub } } })
  }
  it('A8 卡片聚合后续用户原话：排除底稿首条与 AI 消息，保持时间序', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity(), quality: [], standard: null,
      messages: [
        message(1, 'USER', '我要做个海报生成智能体，给市场部用', '2026-10-08T09:30:00'),
        message(2, 'ASSISTANT', '这个需求有多紧急？', '2026-10-08T09:30:10'),
        message(3, 'USER', '紧急，本周内要', '2026-10-08T09:31:00'),
        message(4, 'ASSISTANT', '希望达成什么业务目标？', '2026-10-08T09:31:10'),
        message(5, 'USER', '提升市场部出图效率，原来做一张要半天', '2026-10-08T09:32:00'),
      ]
    })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.find('h2').text()).toBe('需求概述')
    expect(wrapper.find('.content').text()).toBe('我要做个海报生成智能体，给市场部用')
    expect(wrapper.find('.supp-title').text()).toBe('后续对话中的补充原话')
    const rows = wrapper.findAll('.supp-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('紧急，本周内要')
    expect(rows[1].text()).toContain('提升市场部出图效率，原来做一张要半天')
    // A8 底稿与 AI 追问不进入补充原话区
    expect(rows.some(row => row.text().includes('我要做个海报生成智能体'))).toBe(false)
    expect(rows.some(row => row.text().includes('这个需求有多紧急'))).toBe(false)
  })
  it('仅有首轮底稿（无补充原话）时不渲染小节', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity(), quality: [], standard: null,
      messages: [message(1, 'USER', '我要做个海报生成智能体，给市场部用', '2026-10-08T09:30:00')]
    })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.find('.supp-title').exists()).toBe(false)
  })
  it('E区状态面板不渲染，折叠面板仅保留AI对话回放与信息完备度', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity({ changeLogs: [changeLog(9, 'user', 'title', '旧', '新标题')] }),
      quality: [{ key: 'title', code: 'A1', label: '需求标题', status: 'OK', note: '', summary: [] }],
      standard: null,
      messages: [message(1, 'USER', '我要做个海报生成智能体，给市场部用', '2026-10-08T09:30:00')]
    })
    const wrapper = createWrapper(); await flushPromises()
    // E 区面板已隐藏：标题与内容均不出现
    const titles = wrapper.findAll('.van-collapse-item__title').map(node => node.text())
    expect(titles).toEqual(['AI 对话回放', '信息完备度'])
    expect(wrapper.text()).not.toContain('E 区 · 状态信息')
    expect(wrapper.text()).not.toContain('修改次数')
    expect(wrapper.text()).not.toContain('变更留痕')
    // 信息完备度默认收起：collapse 懒渲染，内容不在 DOM
    expect(wrapper.find('[data-quality]').exists()).toBe(false)
    expect(wrapper.find('.history-row').exists()).toBe(false)
  })
})

describe('demand detail 草稿态 A-D 分区占位', () => {
  beforeEach(() => vi.clearAllMocks())
  const standard: Standard = {
    type: 'TECH', name: '科技需求', version: '1', contentHash: 'h',
    elements: [
      { key: 'businessGoal', label: '业务目标', kind: 'text', zone: 'B', path: 'elements.B.businessGoal', required: true },
      { key: 'userRole', label: '目标用户', kind: 'text', zone: 'C', path: 'elements.C.userRole', required: true },
      { key: 'functionDescription', label: '功能描述', kind: 'text', zone: 'D', path: 'elements.D.functionDescription', required: true }
    ],
    commonFields: [], optionalFields: [], subtypeFields: {}, followUpOrder: []
  }
  function createWrapper(): VueWrapper {
    return mount(Detail, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, QualityList: QualityListStub } } })
  }
  it('草稿：四个分区卡片恒显示，无要素分区显示"暂未提取到信息，待补充。"', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity({ status: 'DRAFT', elements: { B: { businessGoal: '晨会前自动产出销量' } } }),
      quality: [], standard, messages: []
    })
    const wrapper = createWrapper(); await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('A · 公共要素')
    expect(text).toContain('B · 业务需求（Why）')
    expect(text).toContain('C · 用户需求（Who/What）')
    expect(text).toContain('D · 功能需求（How）')
    expect(text).toContain('晨会前自动产出销量')
    const placeholders = wrapper.findAll('.zone-empty')
    expect(placeholders).toHaveLength(3)
    expect(placeholders[0].text()).toBe('暂未提取到信息，待补充。')
  })
  it('已提交：无要素分区仍不显示，不出现占位提示', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity({ status: 'SUBMITTED', elements: { B: { businessGoal: '晨会前自动产出销量' } } }),
      quality: [], standard, messages: []
    })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.text()).toContain('B · 业务需求（Why）')
    expect(wrapper.text()).not.toContain('D · 功能需求（How）')
    expect(wrapper.findAll('.zone-empty')).toHaveLength(0)
  })
})

describe('demand detail 需求概述（ext.overview 四段式）', () => {
  beforeEach(() => vi.clearAllMocks())
  function createWrapper(): VueWrapper {
    return mount(Detail, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, QualityList: QualityListStub } } })
  }
  it('有概述时渲染四段标签与文本，不再回退展示 A8 原文与补充原话', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity({
        ext: {
          overview: {
            problem: '市场部做海报要半天｜出图效率低',
            userScene: '市场部员工在活动上线前制作海报｜活动前赶制海报',
            goal: '输入产品信息自动生成营销海报｜海报自动生成',
            acceptance: '生成海报可直接用于朋友圈投放｜海报可直接投放'
          }
        }
      }),
      quality: [], standard: null,
      messages: [
        message(1, 'USER', '我要做个海报生成智能体，给市场部用', '2026-10-08T09:30:00'),
        message(2, 'USER', '紧急，本周内要', '2026-10-08T09:31:00'),
      ]
    })
    const wrapper = createWrapper(); await flushPromises()
    const rows = wrapper.findAll('.ov-row')
    expect(rows.map(row => row.find('strong').text())).toEqual(['问题/机会', '用户&场景', '目标&期望效果', '验收标准'])
    expect(rows[0].find('p').text()).toBe('市场部做海报要半天｜出图效率低')
    expect(rows[3].find('p').text()).toBe('生成海报可直接用于朋友圈投放｜海报可直接投放')
    // 概述存在时不再显示原文回退与补充原话小节
    expect(wrapper.find('.supp-title').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('后续对话中的补充原话')
  })
  it('缺段概述只渲染有值的段；AI 对话回放紧随需求概述卡片', async () => {
    mocks.getDemand.mockResolvedValue({
      demand: entity({ ext: { overview: { problem: '只有痛点｜低效' } } }),
      quality: [], standard: null,
      messages: [message(1, 'USER', '我要做个海报生成智能体，给市场部用', '2026-10-08T09:30:00')]
    })
    const wrapper = createWrapper(); await flushPromises()
    const rows = wrapper.findAll('.ov-row')
    expect(rows).toHaveLength(1)
    expect(rows[0].find('strong').text()).toBe('问题/机会')
    // 回放卡片在概述卡片正后方
    const cards = wrapper.findAll('.detail-card')
    const overviewIdx = cards.findIndex(card => card.find('h2').exists() && card.find('h2').text() === '需求概述')
    const playbackIdx = cards.findIndex(card => card.classes().includes('playback'))
    expect(overviewIdx).toBeGreaterThanOrEqual(0)
    expect(playbackIdx).toBe(overviewIdx + 1)
  })
})

describe('demand detail 撤销入口', () => {
  beforeEach(() => vi.clearAllMocks())
  function createWrapper(): VueWrapper {
    return mount(Detail, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, QualityList: QualityListStub } } })
  }
  it('本人草稿显示「撤销草稿」，已提交显示「撤销需求」', async () => {
    mocks.getDemand.mockResolvedValue({ demand: entity({ status: 'DRAFT' }), quality: [], standard: null, messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    const texts = wrapper.findAll('button').map(b => b.text())
    expect(texts.some(t => t.includes('撤销草稿'))).toBe(true)
    expect(texts.some(t => t === '撤销需求')).toBe(false)

    mocks.getDemand.mockResolvedValue({ demand: entity({ status: 'SUBMITTED' }), quality: [], standard: null, messages: [] })
    const wrapper2 = createWrapper(); await flushPromises()
    const texts2 = wrapper2.findAll('button').map(b => b.text())
    expect(texts2.some(t => t === '撤销需求')).toBe(true)
    expect(texts2.some(t => t.includes('撤销草稿'))).toBe(false)
  })
  it('非本人草稿不显示撤销入口', async () => {
    mocks.getDemand.mockResolvedValue({ demand: entity({ submitterId: 2 }), quality: [], standard: null, messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.findAll('button').some(b => b.text().includes('撤销'))).toBe(false)
  })
})
