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
    { key: 'snapshot', label: '快照要素', kind: 'text', zone: 'A', system: true },
    { key: 'businessGoal', label: '业务目标', kind: 'text', zone: 'B', path: 'elements.B.businessGoal', required: true },
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
  it('按填写状态与质量清单渲染已填/待补充pill', () => {
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form(), quality: [{ key: 'userRole', label: '目标用户', status: 'OK', note: '', attempts: 0 }] }, global: { stubs } })
    const rows = wrapper.findAll('.el')
    const pillOf = (label: string) => rows.find(row => row.text().includes(label))!.find('.pill')
    expect(pillOf('需求标题').text()).toBe('已填')
    expect(pillOf('业务目标').text()).toBe('已填')
    expect(pillOf('功能描述').text()).toBe('待补充')
    // 质量清单 OK 优先于值为空
    expect(pillOf('目标用户').text()).toBe('已填')
  })
  it('点击字段行emit edit-field，业务需求确认后B区带必填标记', async () => {
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form(), businessConfirmed: true }, global: { stubs } })
    expect(wrapper.text()).toContain('业务需求 · 必填')
    const row = wrapper.findAll('.el').find(item => item.text().includes('业务目标'))!
    await row.trigger('click')
    expect(wrapper.emitted('edit-field')?.[0]?.[0]).toMatchObject({ key: 'businessGoal' })
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
  it('用户确认过的归类显示"已确认"；未产生判型数据不渲染标签', () => {
    const value = form()
    value.ext = { typeRecognition: { business: 0.2, confirmed: 'none' as const } }
    const wrapper = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: value }, global: { stubs } })
    expect(wrapper.text()).toContain('归类：日常功能需求')
    expect(wrapper.text()).toContain('已确认 · 点我可改')
    const fresh = mount(FormSnapshotCard, { props: { defaultExpanded: true, standard, form: form() }, global: { stubs } })
    expect(fresh.find('.type-row').exists()).toBe(false)
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
  it('最低标准必填字段标注红色星号，B区条件必填与system字段不标注', () => {
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
  it('默认折叠：只显示必填进度与归类标签，点击标题栏展开/收起要素区', async () => {
    const value = form()
    value.ext = { typeRecognition: { business: 0.9 } }
    const wrapper = mount(FormSnapshotCard, { props: { standard, form: value, businessConfirmed: true }, global: { stubs } })
    // 折叠态：要素区不渲染，头部显示必填进度（12项最低标准中本fixture占5项、已填3项），归类标签保持可见可点
    expect(wrapper.find('.zone').exists()).toBe(false)
    expect(wrapper.text()).toContain('必填 3/5')
    expect(wrapper.find('.type-row').exists()).toBe(true)
    await wrapper.find('.type-row').trigger('click')
    expect(wrapper.emitted('edit-type')).toBeTruthy()
    expect(wrapper.find('.zone').exists()).toBe(false)
    // 展开 → 收起
    await wrapper.find('.card-title').trigger('click')
    expect(wrapper.find('.zone').exists()).toBe(true)
    expect(wrapper.text()).toContain('点任意一项可直接修改')
    await wrapper.find('.card-title').trigger('click')
    expect(wrapper.find('.zone').exists()).toBe(false)
  })
})
