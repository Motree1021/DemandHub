import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import AgentChatPanel from '@/components/AgentChatPanel.vue'
import type { GuidePayload, GuideRequest } from '@/api/sse'
const mocks = vi.hoisted(() => ({ messages: vi.fn(), stream: vi.fn() }))
vi.mock('@/api/agent', async () => ({ agentSessionMessages: mocks.messages, guideChatStream: mocks.stream, StreamError: (await import('@/api/sse')).StreamError }))
const FieldStub = defineComponent({ props: ['modelValue', 'disabled'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />' })
const ButtonStub = defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' })
const wrappers: VueWrapper[] = []
function createWrapper(props: Record<string, unknown> = {}) {
  const prepare = vi.fn().mockResolvedValue({ demandId: 1, sessionId: 11, revision: 1 })
  const wrapper = mount(AgentChatPanel, { props: { demandId: 1, sessionId: 11, revision: 1, prepare, ...props }, global: { stubs: { 'van-field': FieldStub, 'van-button': ButtonStub, 'van-icon': true, 'van-notice-bar': true } } })
  wrappers.push(wrapper); return wrapper
}
function payload(request: GuideRequest, extra: Partial<GuidePayload> = {}): GuidePayload {
  return { ...request, revision: request.revision + 1, structured: { title: '已保存', demandTypeCode: 'TECH', content: '需求', urgency: 'NORMAL', expectDeliveryAt: null, ext: {} }, fieldSources: {}, missing: [], elements: [], askedTarget: null, canSubmit: true, guidanceComplete: true, qualityComplete: false, ready: true, quickReplies: [], ...extra }
}
async function sendAndResolve(wrapper: VueWrapper, extra: Partial<GuidePayload> = {}) {
  mocks.stream.mockImplementationOnce(async request => payload(request, extra))
  await wrapper.find('textarea').setValue('我们部门每天晨会要统计各渠道销量')
  await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click')
  await flushPromises()
}
beforeEach(() => { vi.clearAllMocks(); mocks.messages.mockResolvedValue([]) })
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

describe('FR-01 判型自动生效（方案A）', () => {
  it('business≥0.5且未确认时不再弹出确认卡，归类标签由要素实时卡承载', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await sendAndResolve(wrapper, { typeRecognition: { business: 0.9, user: 0.2, function: 0.3, evidence: { business: '晨会统计销量属于经营分析' } } })
    expect(wrapper.text()).not.toContain('对，是业务需求')
    expect(wrapper.text()).not.toContain('我也说不清')
    expect(wrapper.emitted('confirm-type')).toBeUndefined()
  })
})

describe('BR-T13 粒度提示与受影响要素提示', () => {
  it('too_broad 提示先聚焦并展示收敛标准', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await sendAndResolve(wrapper, { granularityHint: { level: 'too_broad', hint: 'scope', converge: '先聚焦到一个部门的一类报表' } })
    expect(wrapper.text()).toContain('需求有点大，先聚焦')
    expect(wrapper.text()).toContain('收敛标准：先聚焦到一个部门的一类报表')
  })
  it('too_narrow 提示补上下文', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await sendAndResolve(wrapper, { granularityHint: { level: 'too_narrow', hint: 'narrow', converge: '补上使用场景和触发时机' } })
    expect(wrapper.text()).toContain('需求有点细，补上下文')
    expect(wrapper.text()).toContain('收敛标准：补上使用场景和触发时机')
  })
  it('无粒度问题不展示粒度横幅', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await sendAndResolve(wrapper)
    expect(wrapper.text()).not.toContain('需求有点大'); expect(wrapper.text()).not.toContain('需求有点细')
  })
  it('impactHints 逐条展示', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await sendAndResolve(wrapper, { impactHints: ['「业务目标」会被改写', '「验收标准」新增内容'] })
    expect(wrapper.text()).toContain('「业务目标」会被改写')
    expect(wrapper.text()).toContain('「验收标准」新增内容')
  })
})
