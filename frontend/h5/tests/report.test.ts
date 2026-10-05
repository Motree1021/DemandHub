import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, reactive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Vant from 'vant'
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
const FieldStub = defineComponent({ props: ['field', 'modelValue', 'disabled'], emits: ['update:modelValue'], template: '<input :data-field="field.key" :value="modelValue ?? \'\'" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />' })
const QualityStub = defineComponent({ props: ['elements', 'labels'], template: '<div data-quality>{{ elements.map(item => item.status).join(",") }}</div>' })
const SheetStub = defineComponent({ props: ['show', 'demandId', 'sessionId', 'revision', 'prepare'], emits: ['complete', 'busy'], template: '<div data-sheet>{{ demandId }} / {{ sessionId }}</div>' })
const wrappers: VueWrapper[] = []
function createWrapper() {
  const wrapper = mount(Report, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, StandardField: FieldStub, AgentGuideSheet: SheetStub, QualityList: QualityStub } } })
  wrappers.push(wrapper); return wrapper
}
async function clickButton(wrapper: VueWrapper, label: string) { await wrapper.findAll('button').find(button => button.text().includes(label))!.trigger('click'); await flushPromises() }
beforeEach(() => {
  vi.clearAllMocks(); route.query = {}
  mocks.getStandard.mockResolvedValue(standard)
  mocks.createAgentSession.mockImplementation(async id => ({ id: id + 10, demandId: id, status: 'ACTIVE' }))
  mocks.updateDraft.mockImplementation(async (id, payload) => demand(id, { ...payload, revision: payload.expectedRevision + 1 }))
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })

describe('report 草稿与会话恢复', () => {
  it.each([5, 4])('草稿刷新只恢复同revision质量清单（消息revision=%s）', async messageRevision => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { revision: 5, sessionId: 11 }), quality: [], messages: [{ id: 1, role: 'ASSISTANT', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: messageRevision, elements: [{ key: 'businessScenario', status: 'OK', label: '业务场景', note: '', attempts: 0 }] }) }] })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.findComponent(QualityStub).props('elements')).toHaveLength(messageRevision === 5 ? 1 : 0)
  })
  it('未知类型的不完整草稿仍能填写共同字段并启动对应AI会话', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { demandTypeCode: null }), quality: [], messages: [], standard: null })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.find('[data-field="title"]').exists()).toBe(true)
    expect(wrapper.find('[data-field="demandTypeCode"]').exists()).toBe(true)
    expect(wrapper.find('[data-field="content"]').exists()).toBe(true)
    expect(wrapper.find('[data-field="businessScenario"]').exists()).toBe(false)
    await clickButton(wrapper, '用 AI 整理')
    expect(mocks.createAgentSession).toHaveBeenCalledWith(1)
    expect(wrapper.findComponent(SheetStub).props('show')).toBe(true)
  })
  it('SPA两草稿切换和新建重置session、来源、质量', async () => {
    mocks.getDemand.mockImplementation(async id => ({ demand: demand(id, { title: `草稿${id}`, sessionId: id + 10, fieldSources: { title: 'user' } }), quality: [], messages: [] }))
    route.query = { draftId: 1 }; const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.find('[data-field="title"]').element).toHaveProperty('value', '草稿1')
    route.query = { draftId: 2 }; await flushPromises()
    expect(wrapper.find('[data-field="title"]').element).toHaveProperty('value', '草稿2')
    expect(wrapper.findComponent(SheetStub).props('sessionId')).toBe(12)
    route.query = {}; await flushPromises()
    expect(wrapper.find('[data-field="title"]').element).toHaveProperty('value', '')
    expect(wrapper.findComponent(SheetStub).props('sessionId')).toBeNull()
    expect(wrapper.findComponent(SheetStub).props('demandId')).toBeNull()
    mocks.createDraft.mockImplementation(async payload => demand(3, payload))
    await clickButton(wrapper, '保存草稿')
    expect(mocks.createDraft.mock.calls.at(-1)?.[0].fieldSources).toEqual({ demandTypeCode: 'default', urgency: 'default' })
  })
  it('迟到旧草稿响应不覆盖当前草稿', async () => {
    let resolveFirst!: (value: unknown) => void
    mocks.getDemand.mockImplementation(id => id === 1 ? new Promise(resolve => { resolveFirst = resolve }) : Promise.resolve({ demand: demand(2, { title: '第二份' }) }))
    route.query = { draftId: 1 }; const wrapper = createWrapper(); await flushPromises()
    route.query = { draftId: 2 }; await flushPromises()
    resolveFirst({ demand: demand(1, { title: '迟到第一份' }) }); await flushPromises()
    expect(wrapper.find('[data-field="title"]').element).toHaveProperty('value', '第二份')
  })
  it('创建响应丢失刷新后以原ID和内容恢复，再保存后续手改', async () => {
    mocks.createDraft.mockRejectedValueOnce(new Error('连接中断'))
    const first = createWrapper(); await flushPromises()
    await first.find('[data-field="title"]').setValue('已在服务器创建的标题')
    await clickButton(first, '保存草稿')
    const original = mocks.createDraft.mock.calls[0][0]
    expect(JSON.parse(sessionStorage.getItem('demandhub_h5_create_request_7')!)).toEqual(original)
    first.unmount(); wrappers.splice(wrappers.indexOf(first), 1)
    const restored = createWrapper(); await flushPromises()
    expect(restored.find('[data-field="title"]').element).toHaveProperty('value', original.title)
    await restored.find('[data-field="title"]').setValue('刷新后手改标题')
    mocks.createDraft.mockResolvedValueOnce(demand(9, { ...original, revision: 1 }))
    await clickButton(restored, '保存草稿')
    expect(mocks.createDraft.mock.calls[1][0]).toEqual(original)
    expect(mocks.updateDraft).toHaveBeenCalledWith(9, expect.objectContaining({ title: '刷新后手改标题', expectedRevision: 1, fieldSources: expect.objectContaining({ title: 'user' }) }))
    expect(sessionStorage.getItem('demandhub_h5_create_request_7')).toBeNull()
    expect(route.query.draftId).toBe(9)
  })
  it('每次对话前先持久化手填，使用返回revision', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11 }) })
    const wrapper = createWrapper(); await flushPromises()
    await wrapper.find('[data-field="content"]').setValue('手动修改后才对话')
    const context = await wrapper.findComponent(SheetStub).props('prepare')()
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({ expectedRevision: 1, content: '手动修改后才对话', fieldSources: expect.objectContaining({ content: 'user' }) }))
    expect(context).toEqual({ demandId: 1, sessionId: 11, revision: 2 })
  })
  it('重放旧revision不覆盖更新后的草稿或未保存手改', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { title: '新版本', revision: 5, sessionId: 11 }) })
    const wrapper = createWrapper(); await flushPromises()
    const sheet = wrapper.findComponent(SheetStub)
    sheet.vm.$emit('complete', { demandId: 1, sessionId: 11, revision: 4, structured: { title: '旧回放' }, fieldSources: {}, elements: [] }); await flushPromises()
    expect(wrapper.find('[data-field="title"]').element).toHaveProperty('value', '新版本')
    await wrapper.find('[data-field="title"]').setValue('未保存手改')
    sheet.vm.$emit('complete', { demandId: 1, sessionId: 11, revision: 6, structured: { title: '模型' }, fieldSources: {}, elements: [] }); await flushPromises()
    expect(wrapper.find('[data-field="title"]').element).toHaveProperty('value', '未保存手改')
  })
})
