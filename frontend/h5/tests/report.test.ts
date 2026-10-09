import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, reactive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Vant, { showToast } from 'vant'
import Report from '@/views/report/index.vue'
import { ApiError } from '@/api/request'
import type { DemandEntity, Standard } from '@/api/demand'

const mocks = vi.hoisted(() => ({ getDemand: vi.fn(), getStandard: vi.fn(), createDraft: vi.fn(), updateDraft: vi.fn(), submitDemand: vi.fn(), createAgentSession: vi.fn() }))
vi.mock('@/api/demand', () => mocks)
vi.mock('@/api/agent', () => ({ createAgentSession: mocks.createAgentSession }))
vi.mock('@/store/user', () => ({ useUserStore: () => ({ userInfo: { id: 7, isAdmin: false } }) }))
vi.mock('vant', async importOriginal => ({ ...await importOriginal<typeof import('vant')>(), showToast: vi.fn(), showConfirmDialog: vi.fn().mockResolvedValue(undefined) }))
const route = reactive({ query: {} as Record<string, unknown> })
const router = { replace: vi.fn(async value => { if (value && typeof value === 'object') route.query = value.query || {} }), push: vi.fn() }
vi.mock('vue-router', () => ({ useRoute: () => route, useRouter: () => router }))
const standard: Standard = {
  type: 'TECH', name: '科技需求', version: '1', contentHash: 'h',
  elements: [
    { key: 'title', label: '需求标题', kind: 'text', required: true },
    { key: 'demandTypeCode', label: '需求类型', kind: 'enum', required: true, options: { TECH: '科技需求', MATL: '物料需求', TRAIN: '培训需求' } },
    { key: 'content', label: '需求描述', kind: 'text', required: true },
    { key: 'businessScenario', path: 'ext.businessScenario', label: '业务场景', kind: 'text' }
  ],
  commonFields: [{ key: 'urgency', label: '紧急程度', kind: 'enum', options: { NORMAL: '普通' } }], optionalFields: [], subtypeFields: {}, followUpOrder: []
}
function demand(id: number, extra: Partial<DemandEntity> = {}): DemandEntity {
  return { id, demandNo: null, title: '', demandTypeCode: 'TECH', content: '', urgency: 'NORMAL', expectDeliveryAt: null, ext: {}, fieldSources: { demandTypeCode: 'default' }, revision: 1, status: 'DRAFT', sessionId: null, submitterId: 7, quality: [], ...extra } as DemandEntity
}
const PanelStub = defineComponent({ props: ['demandId', 'sessionId', 'revision', 'prepare', 'quality'], emits: ['complete', 'busy', 'edit-field', 'save-draft'], template: '<div data-panel>{{ demandId }} / {{ sessionId }}<slot name="welcome" /></div>' })
const ActionSheetStub = defineComponent({ props: ['show', 'actions'], emits: ['update:show', 'select'], template: '<div v-if="show" data-action-sheet><button v-for="(action, index) in actions" :key="action.name" @click="$emit(\'select\', action, index)">{{ action.name }}</button></div>' })
const FieldEditSheetStub = defineComponent({ props: ['show', 'field', 'value'], emits: ['update:show', 'save'], template: '<div v-if="show" data-field-edit />' })
const wrappers: VueWrapper[] = []
function createWrapper() {
  const wrapper = mount(Report, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, AgentChatPanel: PanelStub, FieldEditSheet: FieldEditSheetStub, 'van-action-sheet': ActionSheetStub } } })
  wrappers.push(wrapper); return wrapper
}
async function clickButton(wrapper: VueWrapper, label: string) { await wrapper.findAll('button').find(button => button.text().includes(label))!.trigger('click'); await flushPromises() }
// 手改要素经要素卡单字段编辑入口（FieldEditSheet）：edit-field 打开、save 落本地
const titleField = standard.elements[0]; const contentField = standard.elements[2]
async function editField(wrapper: VueWrapper, field: Standard['elements'][number], value: unknown) {
  wrapper.findComponent(PanelStub).vm.$emit('edit-field', field); await flushPromises()
  wrapper.findComponent(FieldEditSheetStub).vm.$emit('save', field, value); await flushPromises()
}
async function fieldValue(wrapper: VueWrapper, field: Standard['elements'][number]) {
  wrapper.findComponent(PanelStub).vm.$emit('edit-field', field); await flushPromises()
  return wrapper.findComponent(FieldEditSheetStub).props('value')
}
async function saveDraft(wrapper: VueWrapper) { wrapper.findComponent(PanelStub).vm.$emit('save-draft'); await flushPromises() }
beforeEach(() => {
  vi.clearAllMocks(); route.query = {}
  mocks.getStandard.mockResolvedValue(standard)
  mocks.createAgentSession.mockImplementation(async id => ({ id: id + 10, demandId: id, status: 'ACTIVE' }))
  mocks.updateDraft.mockImplementation(async (id, payload) => demand(id, { ...payload, revision: payload.expectedRevision + 1 }))
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })

describe('report 对话页骨架', () => {
  it('新用户进入展示欢迎语与三个入口', async () => {
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.text()).toContain('需求收集助手')
    expect(wrapper.text()).toContain('我有一个清晰的需求要提报')
    expect(wrapper.text()).toContain('一段话完整需求示例')
    expect(wrapper.text()).toContain('我只有一个模糊想法')
  })
  it('步骤条初始在表达步', async () => {
    const wrapper = createWrapper(); await flushPromises()
    const steps = wrapper.findAll('.step')
    expect(steps.map(step => step.text())).toEqual(['表达', '拆解', '追问', '提交'])
    expect(steps[0].classes()).toContain('on')
  })
  it('点「我只有一个模糊想法」仅展示本地引导，不建草稿/会话/发消息', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await clickButton(wrapper, '我只有一个模糊想法')
    // 本地回显入口语与固定引导语
    expect(wrapper.text()).toContain('请一步步帮我想清楚')
    expect(wrapper.text()).toContain('一步步想清楚')
    // 未做第二步操作：无任何持久化动作
    expect(mocks.createDraft).not.toHaveBeenCalled()
    expect(mocks.updateDraft).not.toHaveBeenCalled()
    expect(mocks.createAgentSession).not.toHaveBeenCalled()
  })
  it('复制示例：写入剪贴板供用户编辑发送，不预写 A8、不代发消息', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const wrapper = createWrapper(); await flushPromises()
    await clickButton(wrapper, '一段话完整需求示例')
    expect(wrapper.text()).toContain('示例一')
    await clickButton(wrapper, '复制示例')
    expect(writeText).toHaveBeenCalledTimes(1)
    expect(String(writeText.mock.calls[0][0])).toContain('渠道')
    expect(vi.mocked(showToast)).toHaveBeenCalledWith('已复制，粘贴到输入框编辑后发送')
    // 不触发草稿保存/会话创建/消息发送
    expect(mocks.createDraft).not.toHaveBeenCalled()
    expect(mocks.updateDraft).not.toHaveBeenCalled()
    expect(mocks.createAgentSession).not.toHaveBeenCalled()
  })
})

describe('report 判型改判（方案A）', () => {
  async function pickType(wrapper: VueWrapper, name: string) {
    wrapper.findComponent(PanelStub).vm.$emit('edit-type'); await flushPromises()
    await wrapper.findAll('[data-action-sheet] button').find(button => button.text() === name)!.trigger('click'); await flushPromises()
  }
  it('选「是业务需求」写confirmed=business并保存，来源标user', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { business: 0.9 } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    await pickType(wrapper, '是业务需求')
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({
      ext: expect.objectContaining({ typeRecognition: expect.objectContaining({ business: 0.9, confirmed: 'business' }) }),
      fieldSources: expect.objectContaining({ 'ext.typeRecognition': 'user' })
    }))
  })
  it('选「只是日常功能需求」写confirmed=none', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { business: 0.9 } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    await pickType(wrapper, '只是日常功能需求')
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({
      ext: expect.objectContaining({ typeRecognition: expect.objectContaining({ confirmed: 'none' }) })
    }))
  })
  it('选「让AI判断」清除confirmed恢复自动判定', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { business: 0.9, confirmed: 'business' } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    await pickType(wrapper, '让 AI 判断')
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({
      ext: expect.objectContaining({ typeRecognition: expect.objectContaining({ confirmed: null }) })
    }))
  })
})

describe('report 草稿与会话恢复', () => {
  it.each([5, 4])('草稿刷新只恢复同revision质量清单（消息revision=%s）', async messageRevision => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { revision: 5, sessionId: 11 }), quality: [], messages: [{ id: 1, role: 'ASSISTANT', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: messageRevision, elements: [{ key: 'businessScenario', status: 'OK', label: '业务场景', note: '', attempts: 0 }] }) }] })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.findComponent(PanelStub).props('quality')).toHaveLength(messageRevision === 5 ? 1 : 0)
  })
  it('未知类型的不完整草稿仍能启动对应AI会话', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { demandTypeCode: null }), quality: [], messages: [], standard: null })
    const wrapper = createWrapper(); await flushPromises()
    const context = await wrapper.findComponent(PanelStub).props('prepare')()
    expect(mocks.createAgentSession).toHaveBeenCalledWith(1)
    expect(context).toEqual({ demandId: 1, sessionId: 11, revision: 1 })
  })
  it('SPA两草稿切换和新建重置session、来源、质量', async () => {
    mocks.getDemand.mockImplementation(async id => ({ demand: demand(id, { title: `草稿${id}`, sessionId: id + 10, fieldSources: { title: 'user' } }), quality: [], messages: [] }))
    route.query = { draftId: 1 }; const wrapper = createWrapper(); await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('草稿1')
    route.query = { draftId: 2 }; await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('草稿2')
    expect(wrapper.findComponent(PanelStub).props('sessionId')).toBe(12)
    route.query = {}; await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('')
    expect(wrapper.findComponent(PanelStub).props('sessionId')).toBeNull()
    expect(wrapper.findComponent(PanelStub).props('demandId')).toBeNull()
    mocks.createDraft.mockImplementation(async payload => demand(3, payload))
    await saveDraft(wrapper)
    expect(mocks.createDraft.mock.calls.at(-1)?.[0].fieldSources).toEqual({ demandTypeCode: 'default' })
  })
  it('迟到旧草稿响应不覆盖当前草稿', async () => {
    let resolveFirst!: (value: unknown) => void
    mocks.getDemand.mockImplementation(id => id === 1 ? new Promise(resolve => { resolveFirst = resolve }) : Promise.resolve({ demand: demand(2, { title: '第二份' }) }))
    route.query = { draftId: 1 }; const wrapper = createWrapper(); await flushPromises()
    route.query = { draftId: 2 }; await flushPromises()
    resolveFirst({ demand: demand(1, { title: '迟到第一份' }) }); await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('第二份')
  })
  it('创建响应丢失刷新后以原ID和内容恢复，再保存后续手改', async () => {
    mocks.createDraft.mockRejectedValueOnce(new Error('连接中断'))
    const first = createWrapper(); await flushPromises()
    await editField(first, titleField, '已在服务器创建的标题')
    await saveDraft(first)
    const original = mocks.createDraft.mock.calls[0][0]
    expect(JSON.parse(sessionStorage.getItem('demandhub_h5_create_request_7')!)).toEqual(original)
    first.unmount(); wrappers.splice(wrappers.indexOf(first), 1)
    const restored = createWrapper(); await flushPromises()
    expect(await fieldValue(restored, titleField)).toBe(original.title)
    await editField(restored, titleField, '刷新后手改标题')
    mocks.createDraft.mockResolvedValueOnce(demand(9, { ...original, revision: 1 }))
    await saveDraft(restored)
    expect(mocks.createDraft.mock.calls[1][0]).toEqual(original)
    expect(mocks.updateDraft).toHaveBeenCalledWith(9, expect.objectContaining({ title: '刷新后手改标题', expectedRevision: 1, fieldSources: expect.objectContaining({ title: 'user' }) }))
    expect(sessionStorage.getItem('demandhub_h5_create_request_7')).toBeNull()
    expect(route.query.draftId).toBe(9)
  })
  it('每次对话前先持久化手填，使用返回revision', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11 }) })
    const wrapper = createWrapper(); await flushPromises()
    await editField(wrapper, contentField, '手动修改后才对话')
    const context = await wrapper.findComponent(PanelStub).props('prepare')()
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({ expectedRevision: 1, content: '手动修改后才对话', fieldSources: expect.objectContaining({ content: 'user' }) }))
    expect(context).toEqual({ demandId: 1, sessionId: 11, revision: 2 })
  })
  it('重放旧revision不覆盖更新后的草稿或未保存手改', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { title: '新版本', revision: 5, sessionId: 11 }) })
    const wrapper = createWrapper(); await flushPromises()
    const panel = wrapper.findComponent(PanelStub)
    panel.vm.$emit('complete', { demandId: 1, sessionId: 11, revision: 4, structured: { title: '旧回放' }, fieldSources: {}, elements: [] }); await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('新版本')
    await editField(wrapper, titleField, '未保存手改')
    panel.vm.$emit('complete', { demandId: 1, sessionId: 11, revision: 6, structured: { title: '模型' }, fieldSources: {}, elements: [] }); await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('未保存手改')
  })
})
