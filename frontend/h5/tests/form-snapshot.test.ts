import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import FormSnapshotCard from '@/components/FormSnapshotCard.vue'
import type { DemandForm, Standard } from '@/api/demand'
import { newForm } from '@/utils/form'

const TagStub = defineComponent({ template: '<span><slot /></span>' })
const stubs = { 'van-icon': true, 'van-tag': TagStub }

const standard: Standard = {
  type: 'TECH', name: '科技需求', version: '1', contentHash: 'h',
  elements: [
    { key: 'title', label: '需求标题', kind: 'text', zone: 'A', required: true },
    { key: 'demandTypeCode', label: '需求类型', kind: 'enum', zone: 'A', required: true, options: { TECH: '科技需求', MATL: '物资需求' } },
    { key: 'urgency', label: '紧急程度', kind: 'enum', zone: 'A', required: true, options: { NORMAL: '普通', URGENT: '加急' } },
    { key: 'expectDeliveryAt', label: '期望完成时间', kind: 'date', zone: 'A', required: false },
    { key: 'snapshot', label: '快照要素', kind: 'text', zone: 'A', system: true },
    // 判型与 B 区解耦（2026-10-24 拍板）：B 区要素全部非必填，与后端 tech.yaml 口径一致
    { key: 'businessGoal', label: '业务目标', kind: 'text', zone: 'B', path: 'elements.B.businessGoal', required: false },
    { key: 'userRole', label: '目标用户', kind: 'text', zone: 'C', path: 'elements.C.userRole', required: true },
    { key: 'functionDescription', label: '功能描述', kind: 'text', zone: 'D', path: 'elements.D.functionDescription', required: true }
  ],
  commonFields: [], optionalFields: [], subtypeFields: {}, followUpOrder: []
}
function form(): DemandForm {
  const value = newForm()
  value.title = '渠道销量晨会报表'
  value.demandTypeCode = 'TECH'
  value.urgency = 'NORMAL'
  value.elements = { B: { businessGoal: '晨会前自动产出销量，减少手工统计' } }
  return value
}

describe('FormSnapshotCard 要素实时卡', () => {
  it('按A/B/C/D分区渲染并附白话注释，system快照要素不渲染', () => {
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form() }, global: { stubs } })
    const text = wrapper.text()
    expect(text).toContain('A · 公共要素'); expect(text).toContain('基本信息')
    expect(text).toContain('B · 业务需求'); expect(text).toContain('为什么做、价值是什么')
    expect(text).toContain('C · 用户需求'); expect(text).toContain('谁用、用来做什么')
    expect(text).toContain('D · 功能需求'); expect(text).toContain('系统要做什么')
    expect(text).toContain('需求标题'); expect(text).not.toContain('快照要素')
  })
  it('按填写状态渲染已填/待补充/选填三态pill，选填未填不再挂假待办', () => {
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form(), quality: [{ key: 'userRole', label: '目标用户', status: 'OK', note: '', attempts: 0 }] }, global: { stubs } })
    const rows = wrapper.findAll('.el')
    const pillOf = (label: string) => rows.find(row => row.text().includes(label))!.find('.pill')
    expect(pillOf('需求标题').text()).toBe('已填')
    expect(pillOf('业务目标').text()).toBe('已填')
    expect(pillOf('功能描述').text()).toBe('待补充')
    // 质量清单 OK 优先于值为空
    expect(pillOf('目标用户').text()).toBe('已填')
    // 选填项（期望完成时间）未填显示灰胶囊「选填」，不与必填项的「待补充」混淆
    const optional = pillOf('期望完成时间')
    expect(optional.text()).toBe('选填')
    expect(optional.classes()).toContain('optional')
    // B 区全量选填（2026-10-24 拍板判型解耦）：业务目标未填显示「选填」
    const plain = form()
    delete plain.elements.B
    const bWrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: plain }, global: { stubs } })
    const bPill = bWrapper.findAll('.el').find(row => row.text().includes('业务目标'))!.find('.pill')
    expect(bPill.text()).toBe('选填')
    expect(bPill.classes()).toContain('optional')
  })
  it('点击字段行emit edit-field；B区不标星，B1空缺显示「先空着，不影响提交」灰标签', async () => {
    // 判型与 B 区解耦（2026-10-24 拍板）：B 区全部非必填——不标星、不再挂「业务需求·必填」，
    // B1 空缺时灰字提示「先空着，不影响提交」（不标红不催办）；填写后标记消失
    const emptyB = form()
    delete emptyB.elements.B
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: emptyB, businessConfirmed: true }, global: { stubs } })
    expect(wrapper.text()).toContain('先空着，不影响提交')
    expect(wrapper.text()).not.toContain('业务需求 · 必填')
    const row = wrapper.findAll('.el').find(item => item.text().includes('业务目标'))!
    expect(row.find('.req').exists()).toBe(false)
    await row.trigger('click')
    expect(wrapper.emitted('edit-field')?.[0]?.[0]).toMatchObject({ key: 'businessGoal' })
    // B1 已填：灰标签消失
    const filledB = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form(), businessConfirmed: true }, global: { stubs } })
    expect(filledB.text()).not.toContain('先空着，不影响提交')
  })
  it('D9 建议方案选填：未填显示「选填」胶囊不标星，不计入必填分母', () => {
    // 方案⑤（2026-10-12 拍板）：提报人设想的候选方案/实现路径，选填供受理方评估、永不追问
    const d9Standard = { ...standard, elements: [...standard.elements, { key: 'proposedSolution', label: '建议方案', kind: 'text', zone: 'D', path: 'elements.D.proposedSolution', required: false }] }
    const empty = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard: d9Standard, form: form() }, global: { stubs } })
    const emptyRow = empty.findAll('.el').find(row => row.text().includes('建议方案'))!
    expect(emptyRow.find('.pill').text()).toBe('选填')
    expect(emptyRow.find('.req').exists()).toBe(false)
    // D9 不进必填分母：折叠态进度仍是 fixture 原必填口径「必填 3/5」（title/urgency/demandTypeCode 已填）
    const collapsed = mount(FormSnapshotCard, { props: { standard: d9Standard, form: form() }, global: { stubs } })
    expect(collapsed.text()).toContain('必填 3/5')
    // 填写后显示已填胶囊，可点击编辑
    const filled = form()
    filled.elements.D = { proposedSolution: '两个方案2选1：迁到公司H5服务器用fenhang域名，或为coze申请企业域名并备案' }
    const filledWrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard: d9Standard, form: filled }, global: { stubs } })
    const filledRow = filledWrapper.findAll('.el').find(row => row.text().includes('建议方案'))!
    expect(filledRow.find('.pill').text()).toBe('已填')
  })
  it('AI判型展示归类标签与"AI判断"来源，点击emit edit-type', async () => {
    const value = form()
    value.ext = { typeRecognition: { business: 0.9 } }
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: value, businessConfirmed: true }, global: { stubs } })
    expect(wrapper.text()).toContain('归类：业务需求')
    expect(wrapper.text()).toContain('AI 判断 · 点我可改')
    await wrapper.find('.type-row').trigger('click')
    expect(wrapper.emitted('edit-type')).toBeTruthy()
  })
  it('归类行双标签（方案④）：口径与归类并排，light 显示「轻量提报」、standard 显示「常规提报」', () => {
    const mountWithMode = (mode: unknown) => {
      const value = form()
      value.ext = { typeRecognition: { business: 0.9 }, ...(mode ? { mode } : {}) }
      return mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: value, businessConfirmed: true }, global: { stubs } })
    }
    const light = mountWithMode({ level: 'light', evidence: '换logo' })
    expect(light.text()).toContain('归类：业务需求')
    expect(light.text()).toContain('轻量提报')
    expect(light.text()).not.toContain('常规提报')
    const standardMode = mountWithMode({ level: 'standard', evidence: '新功能' })
    expect(standardMode.text()).toContain('常规提报')
    // 无 mode（未判定）缺省常规口径，双标签仍完整
    expect(mountWithMode(undefined).text()).toContain('常规提报')
  })
  it('用户确认过的归类显示"已确认"；未产生判型数据不渲染标签', () => {
    const value = form()
    value.ext = { typeRecognition: { business: 0.2, confirmed: 'function' as const } }
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: value }, global: { stubs } })
    expect(wrapper.text()).toContain('归类：功能需求')
    expect(wrapper.text()).toContain('已确认 · 点我可改')
    const fresh = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form() }, global: { stubs } })
    expect(fresh.find('.type-row').exists()).toBe(false)
  })
  it('非业务按层级兜底显示（2026-10-24 拍板档位对齐）：business<0.7 时 user≥0.7→用户需求，否则→功能需求', () => {
    const mountWith = (recognition: Record<string, unknown>) => {
      const value = form()
      value.ext = { typeRecognition: recognition }
      // 父组件（report 页）按层级规则算好 businessConfirmed 传入：business≥0.7（主句级起点）即 true
      const businessConfirmed = ((recognition.business as number) ?? 0) >= 0.7
      return mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: value, businessConfirmed }, global: { stubs } }).text()
    }
    // 需求1 语音生成智能体：business 0.2<0.7 → 看 user 0.85≥0.7 → 用户需求
    expect(mountWith({ business: 0.2, user: 0.85, function: 0.6 })).toContain('归类：用户需求')
    // 需求2 日均规模曲线：business 0.6 为收益从句顶格分，不过 0.7 判线；user 0.6 同为从句级也不过线 → 功能需求
    // （口径演变：2026-10-10 占优→功能 / 2026-10-24 层级 0.5→业务 / 2026-10-24 档位对齐 0.7→功能）
    expect(mountWith({ business: 0.6, user: 0.6, function: 0.8 })).toContain('归类：功能需求')
    // business/user 均 <0.7 → 功能需求兜底（function 不参与比较）
    expect(mountWith({ business: 0.3, user: 0.4, function: 0.7 })).toContain('归类：功能需求')
  })
  it('无标准或无字段时不渲染卡片', () => {
    const wrapper = mount(FormSnapshotCard, { props: { standard: null, form: form() }, global: { stubs } })
    expect(wrapper.find('.snapshot-card').exists()).toBe(false)
    const empty = mount(FormSnapshotCard, { props: { standard: { ...standard, elements: [] }, form: form() }, global: { stubs } })
    expect(empty.find('.snapshot-card').exists()).toBe(false)
  })
  it('枚举字段显示选项中文值而非英文代码', () => {
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form() }, global: { stubs } })
    const rows = wrapper.findAll('.el')
    const valOf = (label: string) => rows.find(row => row.text().includes(label))!.find('.val')
    expect(valOf('需求类型').text()).toBe('科技需求')
    expect(valOf('紧急程度').text()).toBe('普通')
    expect(wrapper.text()).not.toContain('TECH')
    expect(wrapper.text()).not.toContain('NORMAL')
  })
  it('基础必填字段标注红色星号；非业务需求时B区与system字段不标注', () => {
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form() }, global: { stubs } })
    const rows = wrapper.findAll('.el')
    const hasStar = (label: string) => rows.find(row => row.text().includes(label))!.find('.req').exists()
    expect(hasStar('需求标题')).toBe(true)
    expect(hasStar('需求类型')).toBe(true)
    expect(hasStar('紧急程度')).toBe(true)
    expect(hasStar('目标用户')).toBe(true)
    expect(hasStar('功能描述')).toBe(true)
    expect(hasStar('业务目标')).toBe(false)
    expect(wrapper.findAll('.req')).toHaveLength(5)
  })
  it('默认折叠：只显示必填进度，归类行随要素区一起折叠，点击标题栏展开/收起', async () => {
    const value = form()
    value.ext = { typeRecognition: { business: 0.9 } }
    const wrapper = mount(FormSnapshotCard, { props: { standard, form: value, businessConfirmed: true }, global: { stubs } })
    // 折叠态：要素区与归类行均不渲染；头部基础必填 3/5
    // （2026-10-24 拍板判型解耦：B 区不再必填，折叠态不再追加「业务 Y/N」进度）
    expect(wrapper.find('.zone').exists()).toBe(false)
    expect(wrapper.find('.type-row').exists()).toBe(false)
    expect(wrapper.text()).toContain('必填 3/5')
    expect(wrapper.text()).not.toContain('业务 ')
    // 展开 → 归类行可见可点，要素区渲染
    await wrapper.find('.card-title').trigger('click')
    expect(wrapper.find('.zone').exists()).toBe(true)
    expect(wrapper.find('.type-row').exists()).toBe(true)
    await wrapper.find('.type-row').trigger('click')
    expect(wrapper.emitted('edit-type')).toBeTruthy()
    expect(wrapper.text()).toContain('点任意一项可直接修改')
    // 收起 → 归类行随要素区一起隐藏
    await wrapper.find('.card-title').trigger('click')
    expect(wrapper.find('.zone').exists()).toBe(false)
    expect(wrapper.find('.type-row').exists()).toBe(false)
  })
  // 微需求快速通道（方案②）：AI 判 mode=light 时折叠态显示「轻量提报·必填 X/3」，红星只标最小集；
  // 2026-10-19 拍板：原话（content）移出最小集——系统提取项，非用户提供项
  const lightStandard: Standard = {
    ...standard,
    elements: [...standard.elements,
      { key: 'content', label: '原始提报文本', kind: 'text', zone: 'A', required: false },
      { key: 'acceptanceCriteria', label: '期望效果', kind: 'text', zone: 'D', path: 'elements.D.acceptanceCriteria', required: true }]
  }
  it('light 模式：折叠态显示「轻量」迷你标签+「必填 X/3」，不显示常规必填进度', () => {
    const value = form()
    value.ext = { mode: { level: 'light' } }
    const wrapper = mount(FormSnapshotCard, { props: { standard: lightStandard, form: value }, global: { stubs } })
    // 标题+紧急程度已填，期望效果待补 → 2/3；口径用色块标签展示而非文本「·」拼接
    expect(wrapper.find('.mode-pill').text()).toBe('轻量')
    expect(wrapper.text()).toContain('必填 2/3')
    expect(wrapper.text()).not.toContain('必填 3/7')
  })
  it('light 模式：红星只标最小集3项（标题/紧急程度/期望效果），原话/C/D其余与B区不标星', () => {
    const value = form()
    value.ext = { mode: { level: 'light' } }
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard: lightStandard, form: value }, global: { stubs } })
    const rows = wrapper.findAll('.el')
    const hasStar = (label: string) => rows.find(row => row.text().includes(label))!.find('.req').exists()
    expect(hasStar('需求标题')).toBe(true)
    expect(hasStar('原始提报文本')).toBe(false)
    expect(hasStar('紧急程度')).toBe(true)
    expect(hasStar('期望效果')).toBe(true)
    expect(hasStar('需求类型')).toBe(false)
    expect(hasStar('目标用户')).toBe(false)
    expect(hasStar('功能描述')).toBe(false)
    expect(hasStar('业务目标')).toBe(false)
  })
  it('light 模式：展开态标题行提示轻量口径；standard 草稿不受影响', () => {
    const value = form()
    value.ext = { mode: { level: 'light' } }
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard: lightStandard, form: value }, global: { stubs } })
    expect(wrapper.text()).toContain('轻量提报 · 点任意一项可直接修改')
    const normal = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard: lightStandard, form: form() }, global: { stubs } })
    expect(normal.text()).toContain('点任意一项可直接修改')
    expect(normal.text()).not.toContain('轻量提报 ·')
  })
  it('light 模式：非最小集字段胶囊显示「选填」，最小集缺口仍「待补充」', () => {
    const value = form()
    value.ext = { mode: { level: 'light' } }
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard: lightStandard, form: value }, global: { stubs } })
    const rows = wrapper.findAll('.el')
    const pillOf = (label: string) => rows.find(row => row.text().includes(label))!.find('.pill')
    // 最小集缺口仍是系统在等的必填项
    expect(pillOf('期望效果').text()).toBe('待补充')
    // 不追问不标星的 C/D 字段不再挂一片假「待补充」
    expect(pillOf('目标用户').text()).toBe('选填')
    expect(pillOf('功能描述').text()).toBe('选填')
  })
})
