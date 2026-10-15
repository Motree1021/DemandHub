import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import AgentChatPanel from '@/components/AgentChatPanel.vue'
import { StreamError, type GuidePayload, type GuideRequest } from '@/api/sse'
const mocks = vi.hoisted(() => ({ messages: vi.fn(), stream: vi.fn(), fetchThumb: vi.fn(), downloadAtt: vi.fn(), uploadAtt: vi.fn(), preview: vi.fn(), toast: vi.fn() }))
vi.mock('@/api/agent', async () => ({ agentSessionMessages: mocks.messages, guideChatStream: mocks.stream, StreamError: (await import('@/api/sse')).StreamError }))
// 纯函数（isReplayablePayload/fmtSize 等）走真实实现；附件接口与 toast/图片预览按需覆写
vi.mock('@/api/demand', async importOriginal => ({ ...await importOriginal<typeof import('@/api/demand')>(), fetchAttachmentThumb: mocks.fetchThumb, downloadAttachment: mocks.downloadAtt, uploadAttachment: mocks.uploadAtt }))
vi.mock('vant', async importOriginal => ({ ...await importOriginal<typeof import('vant')>(), showToast: mocks.toast, showImagePreview: mocks.preview }))
const FieldStub = defineComponent({ props: ['modelValue', 'disabled'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />' })
const ButtonStub = defineComponent({ props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' })
const wrappers: VueWrapper[] = []
function createWrapper(props: Record<string, unknown> = {}) {
  const prepare = vi.fn().mockResolvedValue({ demandId: 1, sessionId: 11, revision: 1 })
  const wrapper = mount(AgentChatPanel, { props: { demandId: 1, sessionId: 11, revision: 1, prepare, ...props }, global: { stubs: { 'van-field': FieldStub, 'van-button': ButtonStub, 'van-icon': true, 'van-notice-bar': true, 'van-action-sheet': true } } })
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
  it('1401允许手填且保留可重试请求，重试后恢复结果', async () => {
    mocks.stream.mockRejectedValueOnce(new StreamError(1401, 'AI 暂不可用')).mockImplementationOnce(async request => payload(request))
    const { wrapper } = createWrapper(); await flushPromises(); await send(wrapper)
    expect(wrapper.find('textarea').element).toHaveProperty('value', '同一句需求')
    expect(wrapper.emitted('unavailable')?.[0]).toEqual([true])
    await retry(wrapper)
    expect(wrapper.emitted('complete')?.[0][0]).toMatchObject({ qualityComplete: false })
  })
  it('1405内容审核拒绝：展示改写提示、不降级、清pending无重试按钮', async () => {
    mocks.stream.mockRejectedValueOnce(new StreamError(1405, '这段文字未能通过平台内容安全审核，请调整表述后重试'))
    const { wrapper } = createWrapper(); await flushPromises(); await send(wrapper)
    // 输入框恢复原文供改写；提示文案不含"可重试"误导后缀；不出现"重试上一条"；不触发AI不可用降级
    expect(wrapper.find('textarea').element).toHaveProperty('value', '同一句需求')
    expect(wrapper.text()).toContain('这段文字未能通过平台内容安全审核，请调整表述后重试')
    expect(wrapper.text()).not.toContain('可重试恢复已保存结果')
    expect(sessionStorage.getItem('demandhub_h5_pending_1')).toBeNull()
    expect(wrapper.findAll('button').some(button => button.text() === '重试上一条')).toBe(false)
    expect(wrapper.emitted('unavailable')).toBeUndefined()
    // 用户改写后正常重发：走新请求
    mocks.stream.mockImplementationOnce(async request => payload(request))
    await send(wrapper, '调整后的表述')
    expect(mocks.stream.mock.calls[1][0].message).toBe('调整后的表述')
    expect(wrapper.emitted('complete')?.[0][0]).toMatchObject({ qualityComplete: false })
  })
})

describe('手改要素播报卡片', () => {
  it('播报消息渲染为改动手卡片：标题、改为新值、旧值分层', async () => {
    mocks.messages.mockResolvedValue([
      { id: 1, sessionId: 11, role: 'ASSISTANT', content: '你已手动更新了「验收标准」：由「旧内容」改为「新内容」', structuredPayload: JSON.stringify({ kind: 'manualChange', changes: [{ action: 'update', label: '验收标准', old: '旧内容', new: '新内容' }] }) },
      { id: 2, sessionId: 11, role: 'ASSISTANT', content: '你已手动填写了「紧急程度」：紧急', structuredPayload: JSON.stringify({ kind: 'manualChange', changes: [{ action: 'fill', label: '紧急程度', old: '', new: '紧急' }] }) },
    ])
    const { wrapper } = createWrapper(); await flushPromises()
    const cards = wrapper.findAll('.change-bubble')
    expect(cards).toHaveLength(2)
    expect(cards[0].find('.change-head').text()).toBe('你已手动更新了「验收标准」')
    expect(cards[0].findAll('.change-value')[0].text()).toBe('新内容')
    expect(cards[0].findAll('.change-value')[1].text()).toBe('旧内容')
    expect(cards[0].find('.change-tag.new').text()).toBe('改为')
    expect(cards[0].find('.change-tag.old').text()).toBe('原来')
    // fill 无「原来」行，只显示「内容」与新值
    expect(cards[1].find('.change-head').text()).toBe('你已手动填写了「紧急程度」')
    expect(cards[1].find('.change-tag.old').exists()).toBe(false)
    expect(cards[1].find('.change-tag').text()).toBe('内容')
    expect(cards[1].find('.change-value.new').text()).toBe('紧急')
  })
  it('播报在最后不挡质量清单回放：回放仍取更早的对话结果消息', async () => {
    mocks.messages.mockResolvedValue([
      { id: 1, sessionId: 11, role: 'ASSISTANT', content: 'AI回复', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: 2, quickReplies: [], elements: [{ key: 'acceptanceCriteria', status: 'OK', label: '验收标准', note: '', attempts: 0 }] }) },
      { id: 2, sessionId: 11, role: 'ASSISTANT', content: '你已手动更新了「验收标准」', structuredPayload: JSON.stringify({ kind: 'manualChange', changes: [{ action: 'update', label: '验收标准', old: '旧', new: '新' }] }) },
    ])
    const { wrapper } = createWrapper({ revision: 2 }); await flushPromises()
    expect(wrapper.emitted('complete')?.[0][0]).toMatchObject({ revision: 2, elements: [{ key: 'acceptanceCriteria' }] })
  })
})

describe('附件消息卡片与上传（阶段一）', () => {
  const SheetStub = defineComponent({
    props: ['show', 'actions', 'description'],
    emits: ['update:show', 'select'],
    template: `<div v-if="show" data-sheet><p>{{ description }}</p><button v-for="(action, index) in actions" :key="action.name" data-action @click="$emit('select', action, index)">{{ action.name }}</button></div>`,
  })
  function mountPanel() {
    const prepare = vi.fn().mockResolvedValue({ demandId: 1, sessionId: 11, revision: 1 })
    const wrapper = mount(AgentChatPanel, { props: { demandId: 1, sessionId: 11, revision: 1, prepare }, global: { stubs: { 'van-field': FieldStub, 'van-button': ButtonStub, 'van-icon': true, 'van-notice-bar': true, 'van-action-sheet': SheetStub } } })
    wrappers.push(wrapper); return { wrapper, prepare }
  }
  beforeEach(() => { mocks.fetchThumb.mockRejectedValue(new Error('缩略图离线')); mocks.downloadAtt.mockResolvedValue(undefined) })

  it('用户上传的文档渲染附件卡片（mine 样式、名称与大小），点击调下载；AI 固定回执按普通文本气泡渲染', async () => {
    mocks.messages.mockResolvedValue([
      { id: 1, sessionId: 11, role: 'USER', content: '[上传附件] 验收说明.pdf', structuredPayload: JSON.stringify({ kind: 'attachment', attachmentId: 9, fileName: '验收说明.pdf', fileKind: 'DOC', size: 5242880 }), createdAt: '2026-10-10T10:00:00' },
      { id: 2, sessionId: 11, role: 'ASSISTANT', content: '收到附件「验收说明.pdf」，我暂时看不了图片或文档里的内容。', structuredPayload: JSON.stringify({ kind: 'attachmentReceipt', attachmentId: 9, fileName: '验收说明.pdf' }), createdAt: '2026-10-10T10:00:05' },
    ])
    const { wrapper } = mountPanel(); await flushPromises()
    const bubbles = wrapper.findAll('.attach-bubble')
    expect(bubbles).toHaveLength(1) // AI 回执不算附件卡片
    expect(bubbles[0].classes()).toContain('mine')
    expect(bubbles[0].text()).toContain('验收说明.pdf')
    expect(bubbles[0].text()).toContain('5.0MB · 点击查看')
    expect(wrapper.text()).toContain('收到附件「验收说明.pdf」')
    await bubbles[0].trigger('click'); await flushPromises()
    expect(mocks.downloadAtt).toHaveBeenCalledWith(1, 9, '验收说明.pdf')
  })
  it('图片附件：缩略图就绪前显示加载占位，就绪后渲染缩略图并支持全屏预览', async () => {
    let resolveThumb!: (url: string) => void
    mocks.fetchThumb.mockImplementationOnce(() => new Promise<string>(resolve => { resolveThumb = resolve }))
    mocks.messages.mockResolvedValue([
      { id: 1, sessionId: 11, role: 'USER', content: '[上传附件] 原型图.png', structuredPayload: JSON.stringify({ kind: 'attachment', attachmentId: 8, fileName: '原型图.png', fileKind: 'IMAGE', size: 1024 }), createdAt: '2026-10-10T10:00:00' },
    ])
    const { wrapper } = mountPanel(); await flushPromises()
    expect(mocks.fetchThumb).toHaveBeenCalledWith(1, 8)
    expect(wrapper.find('.attach-pending').text()).toBe('图片加载中…')
    resolveThumb('blob:thumb-8'); await flushPromises()
    expect(wrapper.find('img.attach-thumb').attributes('src')).toBe('blob:thumb-8')
    await wrapper.find('.attach-bubble').trigger('click')
    expect(mocks.preview).toHaveBeenCalledWith({ images: ['blob:thumb-8'], closeable: true })
  })
  it('附件回执不参与质量快照回放：回放仍取更早的真实结果消息', async () => {
    mocks.messages.mockResolvedValue([
      { id: 1, sessionId: 11, role: 'ASSISTANT', content: 'AI 回复正文', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: 2, quickReplies: [], elements: [] }) },
      { id: 2, sessionId: 11, role: 'ASSISTANT', content: '收到附件，我暂时看不了图片或文档里的内容。', structuredPayload: JSON.stringify({ kind: 'attachmentReceipt', attachmentId: 8, fileName: '原型图.png' }), createdAt: '2026-10-10T10:00:05' },
    ])
    const { wrapper } = mountPanel(); await flushPromises()
    expect(wrapper.emitted('complete')?.[0][0]).toMatchObject({ revision: 2 })
  })
  it('「＋」面板含多模态提示，选择来源后直传文件：先保草稿再上传，成功后刷新历史并播报 busy', async () => {
    const { wrapper, prepare } = mountPanel(); await flushPromises()
    await wrapper.find('.attach-btn').trigger('click'); await flushPromises()
    const sheet = wrapper.find('[data-sheet]')
    expect(sheet.exists()).toBe(true)
    expect(sheet.text()).toContain('AI 暂不支持识别附件内容')
    // 第三项「从微信/企微选择文件」为分期预留位：点击仅提示即将支持，不触发上传
    const wechat = sheet.findAll('[data-action]').find(button => button.text().includes('微信'))!
    await wechat.trigger('click'); await flushPromises()
    expect(mocks.toast).toHaveBeenCalledWith(expect.stringContaining('即将支持'))
    expect(mocks.uploadAtt).not.toHaveBeenCalled()
    // 选择「上传文档」后模拟选中文件：先保存草稿（prepare）再上传，成功后重拉历史
    const docAction = sheet.findAll('[data-action]').find(button => button.text().includes('上传文档'))!
    await docAction.trigger('click')
    const file = new File(['demo'], '验收说明.pdf', { type: 'application/pdf' })
    const inputs = wrapper.findAll('input[type="file"]')
    expect(inputs).toHaveLength(2)
    Object.defineProperty(inputs[1].element, 'files', { value: [file], configurable: true })
    await inputs[1].trigger('change'); await flushPromises()
    expect(prepare).toHaveBeenCalledTimes(1)
    expect(mocks.uploadAtt).toHaveBeenCalledWith(1, file)
    expect(mocks.messages).toHaveBeenCalledTimes(2) // 挂载时一次 + 上传成功刷新一次
    const busy = wrapper.emitted('busy')!
    expect(busy[0]).toEqual([true])
    expect(busy[busy.length - 1]).toEqual([false])
    expect(wrapper.find('.uploading-hint').exists()).toBe(false)
  })
})
