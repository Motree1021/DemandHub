import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import Vant from 'vant'
import StandardField from '@/components/StandardField.vue'
describe('动态标准字段', () => {
  it('单根接收AI高亮class，不产生fragment attrs警告', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = mount(StandardField, { props: { field: { key: 'title', label: '标题', kind: 'text' }, modelValue: '当前标题' }, attrs: { class: 'ai-flash' }, global: { plugins: [Vant] } })
    expect(wrapper.classes()).toContain('ai-flash')
    expect(warn).not.toHaveBeenCalled(); wrapper.unmount()
  })
  it('日期控件只发YYYY-MM-DD或null，不隐式变ISO时区时间', async () => {
    const wrapper = mount(StandardField, { props: { field: { key: 'expectDeliveryAt', label: '日期', kind: 'date' }, modelValue: null }, global: { plugins: [Vant] } })
    await wrapper.find('input[type=date]').setValue('2026-10-01')
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['2026-10-01'])
    await wrapper.find('input[type=date]').setValue('')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null]); wrapper.unmount()
  })
  it('enum显示标准提供的标签，空筛选值显示全部', () => {
    const wrapper = mount(StandardField, { props: { field: { key: 'type', label: '类型', kind: 'enum', options: { '': '全部类型', TECH: '科技需求' } }, modelValue: '' }, global: { plugins: [Vant] } })
    expect(wrapper.find('input').element).toHaveProperty('value', '全部类型'); wrapper.unmount()
  })
})
