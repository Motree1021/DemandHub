// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Vant from 'vant'
import DemandCard from '@/components/DemandCard.vue'
import { newForm } from '@/utils/form'
import type { DemandEntity } from '@/api/demand'

function entity(over: Partial<DemandEntity> = {}): DemandEntity {
  return {
    ...newForm(), id: 7, demandNo: null, subtypeCode: null, revision: 0, status: 'DRAFT',
    title: '海报生成智能体', content: '', submitterId: 1, submitterName: '管理员', submitterDept: null,
    channel: 'H5', sessionId: null, submittedAt: null, closedAt: null, closeReason: null,
    createdAt: '2026-10-08T09:30:00', updatedAt: '2026-10-08T09:35:00', quality: [], changeLogs: [], ...over
  }
}

describe('DemandCard 草稿操作入口', () => {
  it('草稿显示「继续提报」与「撤销」，点击分别 emit continue/close', async () => {
    const wrapper = mount(DemandCard, { props: { demand: entity(), continuable: true }, global: { plugins: [Vant] } })
    const closeBtn = wrapper.find('.close-btn')
    expect(wrapper.find('.continue').exists()).toBe(true)
    expect(closeBtn.exists()).toBe(true)
    await closeBtn.trigger('click')
    expect(wrapper.emitted('close')).toEqual([[7]])
    // 撤销点击不应触发卡片打开
    expect(wrapper.emitted('open')).toBeUndefined()
  })
  it('已提交需求不显示草稿操作', () => {
    const wrapper = mount(DemandCard, { props: { demand: entity({ status: 'SUBMITTED', demandNo: 'TECH-20261008-001' }), continuable: true }, global: { plugins: [Vant] } })
    expect(wrapper.find('.close-btn').exists()).toBe(false)
    expect(wrapper.find('.continue').exists()).toBe(false)
  })
})

describe('DemandCard 待补充（方案③ NEED_INFO）', () => {
  it('待补充卡片：橙红配色类、「待补充」徽章、「去补充 ›」与「撤销」入口', async () => {
    const wrapper = mount(DemandCard, { props: { demand: entity({ status: 'NEED_INFO', demandNo: 'TECH-20261011-004' }), continuable: true }, global: { plugins: [Vant] } })
    expect(wrapper.find('.demand-card').classes()).toContain('st-need_info')
    expect(wrapper.find('.badge.status').text()).toBe('待补充')
    expect(wrapper.find('.status-icon').html()).toContain('van-icon-replay')
    const continueBtn = wrapper.find('.continue')
    expect(continueBtn.text()).toBe('去补充 ›')
    await continueBtn.trigger('click')
    expect(wrapper.emitted('continue')).toEqual([[7]])
    await wrapper.find('.close-btn').trigger('click')
    expect(wrapper.emitted('close')).toEqual([[7]])
  })
})
