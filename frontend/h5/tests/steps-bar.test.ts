import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import StepsBar from '@/components/StepsBar.vue'

describe('StepsBar 步骤条', () => {
  it('渲染表达→拆解→追问→提交四步（判型 AI 自动生效，无确认步）', () => {
    const wrapper = mount(StepsBar, { props: { step: 0 } })
    expect(wrapper.findAll('.step').map(step => step.text())).toEqual(['表达', '拆解', '追问', '提交'])
  })
  it.each([0, 2, 3])('step=%s 时当前步高亮、已过步标记done、未到步无标记', step => {
    const wrapper = mount(StepsBar, { props: { step } })
    const steps = wrapper.findAll('.step')
    steps.forEach((element, index) => {
      expect(element.classes().includes('on')).toBe(index === step)
      expect(element.classes().includes('done')).toBe(index < step)
    })
  })
})
