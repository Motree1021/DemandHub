import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import AgentChatPanel from '@/components/AgentChatPanel.vue'
import { StreamError, type GuidePayload, type GuideRequest } from '@/api/sse'
const mocks = vi.hoisted(() => ({ messages: vi.fn(), stream: vi.fn() }))
vi.mock('@/api/agent', async () => ({ agentSessionMessages: mocks.messages, guideChatStream: mocks.stream, StreamError: (await import('@/api/sse')).StreamError }))
const FieldStub = defineComponent({ props: ['modelValue', 'disabled'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />' })
const ButtonStub = defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' })
const wrappers: VueWrapper[] = []
function createWrapper(props: Record<string, unknown> = {}) {
  const prepare = vi.fn().mockResolvedValue({ demandId: 1, sessionId: 11, revision: 1 })
  const wrapper = mount(AgentChatPanel, { props: { demandId: 1, sessionId: 11, revision: 1, prepare, ...props }, global: { stubs: { 'van-field': FieldStub, 'van-button': ButtonStub, 'van-icon': true, 'van-notice-bar': true } } })
  wrappers.push(wrapper); return { wrapper, prepare }
}
function payload(request: GuideRequest): GuidePayload { return { ...request, revision: request.revision + 1, structured: { title: '已保存', demandTypeCode: 'TECH', content: '需求', urgency: 'NORMAL', expectDeliveryAt: null, ext: {} }, fieldSources: {}, missing: [], elements: [], askedTarget: null, canSubmit: true, guidanceComplete: true, qualityComplete: false, ready: true, quickReplies: [] } }
async function send(wrapper: VueWrapper, text = '同一句需求') { await wrapper.find('textarea').setValue(text); await wrapper.findAll('button').find(button => button.text() === '发送')!.trigger('click'); await flushPromises() }
async function retry(wrapper: VueWrapper) { await wrapper.findAll('button').find(button => button.text() === '重试上一条')!.trigger('click'); await flushPromises() }
beforeEach(() => { vi.clearAllMocks(); mocks.messages.mockResolvedValue([]); mocks.stream.mockReset() })
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))

describe('Agent当前草稿、失败和幂等恢复', () => {
  it('未知EOF结果保留原输入和requestId，重试不另建请求', async () => {
    mocks.stream.mockRejectedValueOnce(new StreamError(-1, '连接中断')).mockImplementationOnce(async request => payload(request))
    const { wrapper, prepare } = createWrapper(); await flushPromises(); await send(wrapper)
    const request = mocks.stream.mock.calls[0][0]
    expect(wrapper.find('textarea').element).toHaveProperty('value', request.message)
    expect(JSON.parse(sessionStorage.getItem('demandhub_h5_pending_1')!)).toEqual(request)
    expect(wrapper.emitted('complete')).toBeUndefined()
    await retry(wrapper)
    expect(mocks.stream.mock.calls[1][0]).toEqual(request)
    expect(prepare).toHaveBeenCalledOnce()
    expect(wrapper.emitted('complete')?.[0][0]).toMatchObject({ requestId: request.requestId })
    expect(sessionStorage.getItem('demandhub_h5_pending_1')).toBeNull()
  })
  it('明确409保留文字并清失效pending，同一句用最新revision与新ID重发', async () => {
    mocks.stream.mockRejectedValueOnce(new StreamError(409, '草稿已更新')).mockImplementationOnce(async request => payload(request))
    const { wrapper, prepare } = createWrapper(); await flushPromises(); await send(wrapper)
    const first = mocks.stream.mock.calls[0][0]
    expect(wrapper.find('textarea').element).toHaveProperty('value', first.message)
    expect(sessionStorage.getItem('demandhub_h5_pending_1')).toBeNull()
    prepare.mockResolvedValueOnce({ demandId: 1, sessionId: 11, revision: 4 })
    await send(wrapper)
    const next = mocks.stream.mock.calls[1][0]
    expect(next.revision).toBe(4); expect(next.requestId).not.toBe(first.requestId)
  })
  it('中断取消→手改保存→回到草稿→旧请求409→同句新请求恢复', async () => {
    mocks.stream.mockImplementationOnce((_request, _handlers, signal) => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('取消', 'AbortError')))))
      .mockRejectedValueOnce(new StreamError(409, '草稿版本已更新'))
      .mockImplementationOnce(async request => payload(request))
    const { wrapper, prepare } = createWrapper(); await flushPromises(); await send(wrapper)
    const first = mocks.stream.mock.calls[0][0]
    await wrapper.setProps({ demandId: null, sessionId: null }); await flushPromises()
    expect(sessionStorage.getItem('demandhub_h5_pending_1')).not.toBeNull()
    prepare.mockResolvedValue({ demandId: 1, sessionId: 11, revision: 3 })
    await wrapper.setProps({ demandId: 1, sessionId: 11, revision: 3 }); await flushPromises(); await retry(wrapper)
    expect(mocks.stream.mock.calls[1][0]).toEqual(first)
    await send(wrapper)
    expect(mocks.stream.mock.calls[2][0]).toMatchObject({ revision: 3, message: first.message })
    expect(mocks.stream.mock.calls[2][0].requestId).not.toBe(first.requestId)
  })
  it('两草稿快速切换时迟到旧会话不能回写聊天', async () => {
    let resolveOld!: (value: unknown[]) => void
    mocks.messages.mockImplementation(id => id === 11 ? new Promise(resolve => { resolveOld = resolve }) : Promise.resolve([{ id: 2, role: 'USER', content: '第二份聊天' }]))
    const { wrapper } = createWrapper(); await flushPromises()
    await wrapper.setProps({ demandId: 2, sessionId: 22, revision: 2 }); await flushPromises()
    expect(wrapper.text()).toContain('第二份聊天')
    resolveOld([{ id: 1, role: 'USER', content: '迟到第一份聊天' }]); await flushPromises()
    expect(wrapper.text()).toContain('第二份聊天'); expect(wrapper.text()).not.toContain('迟到第一份聊天')
  })
  it('切走后服务端虽保存成功但不能回填旧结果', async () => {
    let resolveOld!: (value: GuidePayload) => void
    mocks.stream.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
    const { wrapper } = createWrapper(); await flushPromises(); await send(wrapper)
    const first = mocks.stream.mock.calls[0][0]
    await wrapper.setProps({ demandId: 2, sessionId: 22 })
    resolveOld(payload(first)); await flushPromises()
    expect(wrapper.emitted('complete')).toBeUndefined()
  })
  it('1401允许手填且保留可重试请求，跳过不显示质量齐备', async () => {
    mocks.stream.mockRejectedValueOnce(new StreamError(1401, 'AI 暂不可用')).mockImplementationOnce(async request => payload(request))
    const { wrapper } = createWrapper(); await flushPromises(); await send(wrapper)
    expect(wrapper.find('textarea').element).toHaveProperty('value', '同一句需求')
    expect(wrapper.emitted('unavailable')?.[0]).toEqual([true])
    await retry(wrapper)
    expect(wrapper.text()).toContain('信息仍有质量缺口')
    expect(wrapper.text()).not.toContain('信息已完善')
  })
})
