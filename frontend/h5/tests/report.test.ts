import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, reactive } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Vant, { showToast, showConfirmDialog } from 'vant'
import Report from '@/views/report/index.vue'
import { ApiError } from '@/api/request'
import type { DemandEntity, Standard } from '@/api/demand'

const mocks = vi.hoisted(() => ({ getDemand: vi.fn(), getStandard: vi.fn(), createDraft: vi.fn(), updateDraft: vi.fn(), submitDemand: vi.fn(), createAgentSession: vi.fn(), changeDemandMode: vi.fn() }))
vi.mock('@/api/demand', async importOriginal => ({ ...await importOriginal<typeof import('@/api/demand')>(), ...mocks }))
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
const PanelStub = defineComponent({ props: ['demandId', 'sessionId', 'revision', 'prepare', 'quality', 'businessConfirmed'], emits: ['complete', 'busy', 'edit-field', 'save-draft', 'submit', 'edit-type'], template: '<div data-panel>{{ demandId }} / {{ sessionId }}<slot name="welcome" /></div>' })
// 方案④：van-action-sheet 升级为 van-popup 双组面板（归类+口径）；stub 留在原地不 teleport，便于 findAll 定位按钮
const PopupStub = defineComponent({ props: ['show'], emits: ['update:show'], template: '<div v-if="show" data-popup><slot /></div>' })
const FieldEditSheetStub = defineComponent({ props: ['show', 'field', 'value', 'saving'], emits: ['update:show', 'save', 'busy'], template: '<div v-if="show" data-field-edit />' })
const wrappers: VueWrapper[] = []
function createWrapper() {
  const wrapper = mount(Report, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, AgentChatPanel: PanelStub, FieldEditSheet: FieldEditSheetStub, 'van-popup': PopupStub } } })
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

describe('report 手改锁定保护（方案一：保存中不给改）', () => {
  it('保存进行中确认要素编辑被拦截：不写表单、不产生新保存、弹层保持打开', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11 }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    const field = { key: 'acceptanceCriteria', label: '验收标准', kind: 'text', zone: 'D', path: 'elements.D.acceptanceCriteria', required: true } as Standard['elements'][number]
    const pending = new Promise<DemandEntity>(() => {})  // 永不完成的保存，模拟在途请求
    mocks.updateDraft.mockImplementationOnce(() => pending)
    wrapper.findComponent(PanelStub).vm.$emit('edit-field', field); await flushPromises()
    const sheet = wrapper.findComponent(FieldEditSheetStub)
    sheet.vm.$emit('save', field, '第一笔改动'); await flushPromises()  // 手改确认→立即落库（该笔被挂起在途）
    expect(sheet.props('saving')).toBe(true)  // 弹层感知保存中
    sheet.vm.$emit('save', field, '音色更具特色'); await flushPromises()
    expect(sheet.props('show')).toBe(true)  // 弹层未被关闭，值不丢
    expect(mocks.updateDraft).toHaveBeenCalledTimes(1)  // 仅第一笔在途，第二笔确认未产生新保存
    expect(await fieldValue(wrapper, field)).toBe('第一笔改动')  // manualEdit 被 locked 拦截，第二笔未写入表单
  })
})
beforeEach(() => {
  vi.clearAllMocks(); route.query = {}
  mocks.getStandard.mockResolvedValue(standard)
  mocks.createAgentSession.mockImplementation(async id => ({ id: id + 10, demandId: id, status: 'ACTIVE' }))
  mocks.updateDraft.mockImplementation(async (id, payload) => demand(id, { ...payload, revision: payload.expectedRevision + 1 }))
  mocks.changeDemandMode.mockImplementation(async (id: number, expectedRevision: number, level: 'light' | 'standard') =>
    demand(id, { revision: expectedRevision + 1, ext: { mode: { level, origin: 'user' } } }))
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
  it('示例区：展开显示两个示例，无复制按钮，不触发持久化', async () => {
    const wrapper = createWrapper(); await flushPromises()
    await clickButton(wrapper, '一段话完整需求示例')
    expect(wrapper.text()).toContain('示例一 · 完整型（目标/场景/功能/验收都带）')
    expect(wrapper.text()).toContain('示例二 · 简洁型（目标/场景/功能/验收精简）')
    expect(wrapper.text()).not.toContain('复制示例')
    // 不触发草稿保存/会话创建/消息发送
    expect(mocks.createDraft).not.toHaveBeenCalled()
    expect(mocks.updateDraft).not.toHaveBeenCalled()
    expect(mocks.createAgentSession).not.toHaveBeenCalled()
  })
})

describe('report 判型改判（方案A）', () => {
  // 面板按钮文本=名称+副说明拼接，按 strong 标题精确定位
  async function pickType(wrapper: VueWrapper, name: string) {
    wrapper.findComponent(PanelStub).vm.$emit('edit-type'); await flushPromises()
    await wrapper.findAll('[data-type-option]').find(button => button.find('strong').text() === name)!.trigger('click'); await flushPromises()
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
  it('选「是用户需求」写confirmed=user', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { user: 0.8 } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    await pickType(wrapper, '是用户需求')
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({
      ext: expect.objectContaining({ typeRecognition: expect.objectContaining({ confirmed: 'user' }) })
    }))
  })
  it('选「是功能需求」写confirmed=function', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { function: 0.8 } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    await pickType(wrapper, '是功能需求')
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({
      ext: expect.objectContaining({ typeRecognition: expect.objectContaining({ confirmed: 'function' }) })
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
  it('业务不占优不激活B区（function更高）；业务占优才传businessConfirmed=true', async () => {
    // 真实样本：「辅助管理层决策」把 business 推到 0.7，但 function=0.8 最高，按「业务占优才激活」不激活 B 区
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { business: 0.7, user: 0.7, function: 0.8 } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.findComponent(PanelStub).props('businessConfirmed')).toBe(false)
    // 业务明显占优（≥0.5 且高于 user/function）才激活
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { business: 0.9, user: 0.3, function: 0.4 } } }), quality: [], messages: [] })
    const dominant = createWrapper(); await flushPromises()
    expect(dominant.findComponent(PanelStub).props('businessConfirmed')).toBe(true)
  })
  it('保存进行中改判被拦截：不写confirmed、不保存、弹层关闭', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { typeRecognition: { business: 0.9 } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    // 手改确认→立即落库，把该笔 mock 成永不返回，形成「保存进行中」窗口
    const field = { key: 'acceptanceCriteria', label: '验收标准', kind: 'text', zone: 'D', path: 'elements.D.acceptanceCriteria', required: true } as Standard['elements'][number]
    const pending = new Promise<DemandEntity>(() => {})
    mocks.updateDraft.mockImplementationOnce(() => pending)
    wrapper.findComponent(PanelStub).vm.$emit('edit-field', field); await flushPromises()
    wrapper.findComponent(FieldEditSheetStub).vm.$emit('save', field, '改动'); await flushPromises()
    wrapper.findComponent(PanelStub).vm.$emit('edit-type'); await flushPromises()
    await wrapper.findAll('[data-type-option]').find(button => button.find('strong').text() === '是业务需求')!.trigger('click'); await flushPromises()
    const saved = mocks.updateDraft.mock.calls.at(-1)?.[1] as { ext?: { typeRecognition?: { confirmed?: string } } }
    expect(saved?.ext?.typeRecognition?.confirmed).toBeUndefined()  // 改判未产生新保存，唯一一笔是手改落库在途请求
    expect(mocks.updateDraft).toHaveBeenCalledTimes(1)
  })
})

describe('report 口径改判（方案④：轻量↔常规双标签与改判弹层）', () => {
  function openPanel(wrapper: VueWrapper) {
    wrapper.findComponent(PanelStub).vm.$emit('edit-type')
  }
  it('常规草稿点「轻量提报」：调改判接口并按响应刷新表单口径', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { mode: { level: 'standard', evidence: 'AI 判定' } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    openPanel(wrapper); await flushPromises()
    // 面板可见：双组结构 + 当前口径勾选在常规
    expect(wrapper.text()).toContain('归类与提报口径')
    expect(wrapper.find('[data-mode-option="standard"]').classes()).toContain('active')
    expect(wrapper.find('[data-mode-option="light"]').classes()).not.toContain('active')
    await wrapper.find('[data-mode-option="light"]').trigger('click'); await flushPromises()
    expect(mocks.changeDemandMode).toHaveBeenCalledWith(1, 1, 'light')
    // 响应刷新表单：口径已切换、面板关闭
    expect(wrapper.findComponent(PopupStub).props('show')).toBe(false)
    expect(wrapper.text()).not.toContain('归类与提报口径')
  })
  it('light 草稿面板勾选轻量；点当前口径项直接关面板不调接口', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, ext: { mode: { level: 'light', evidence: '换logo' } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    openPanel(wrapper); await flushPromises()
    expect(wrapper.find('[data-mode-option="light"]').classes()).toContain('active')
    await wrapper.find('[data-mode-option="light"]').trigger('click'); await flushPromises()
    expect(mocks.changeDemandMode).not.toHaveBeenCalled()
    expect(wrapper.findComponent(PopupStub).props('show')).toBe(false)
  })
  it('打回补充期间轻量口径置灰并提示不可切换', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, status: 'NEED_INFO',
      ext: { mode: { level: 'standard', evidence: '管理员打回待补充' }, returnReason: { reason: '还缺使用场景', returnedBy: '管理员' } } }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    openPanel(wrapper); await flushPromises()
    const light = wrapper.find('[data-mode-option="light"]')
    expect((light.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('.lock-hint').text()).toContain('打回补充期间不可切换为轻量')
    expect(mocks.changeDemandMode).not.toHaveBeenCalled()
  })
  it('新建未保存草稿点口径项：提示先发送需求，不调接口', async () => {
    const wrapper = createWrapper(); await flushPromises()
    openPanel(wrapper); await flushPromises()
    await wrapper.find('[data-mode-option="light"]').trigger('click'); await flushPromises()
    expect(mocks.changeDemandMode).not.toHaveBeenCalled()
    expect(wrapper.findComponent(PopupStub).props('show')).toBe(false)
  })
})

describe('report 草稿与会话恢复', () => {
  it.each([5, 4])('草稿刷新只恢复同revision质量清单（消息revision=%s）', async messageRevision => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { revision: 5, sessionId: 11 }), quality: [], messages: [{ id: 1, role: 'ASSISTANT', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: messageRevision, elements: [{ key: 'businessScenario', status: 'OK', label: '业务场景', note: '', attempts: 0 }] }) }] })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.findComponent(PanelStub).props('quality')).toHaveLength(messageRevision === 5 ? 1 : 0)
  })
  it('手改播报在最后时仍从更早的对话消息恢复质量清单', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { revision: 5, sessionId: 11 }), quality: [], messages: [
      { id: 1, role: 'ASSISTANT', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: 5, elements: [{ key: 'businessScenario', status: 'OK', label: '业务场景', note: '', attempts: 0 }] }) },
      { id: 2, role: 'ASSISTANT', content: '你已手动更新了「业务场景」', structuredPayload: JSON.stringify({ kind: 'manualChange', changes: [{ action: 'update', label: '业务场景', old: '旧', new: '新' }] }) },
    ] })
    const wrapper = createWrapper(); await flushPromises()
    expect(wrapper.findComponent(PanelStub).props('quality')).toHaveLength(1)
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
  it('重放旧revision不覆盖更新后的草稿；手改立即落库后更低的AI回放也不覆盖', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { title: '新版本', revision: 5, sessionId: 11 }) })
    const wrapper = createWrapper(); await flushPromises()
    const panel = wrapper.findComponent(PanelStub)
    panel.vm.$emit('complete', { demandId: 1, sessionId: 11, revision: 4, structured: { title: '旧回放' }, fieldSources: {}, elements: [] }); await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('新版本')
    await editField(wrapper, titleField, '已保存手改')
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({ title: '已保存手改', notifyChanges: true }))
    panel.vm.$emit('complete', { demandId: 1, sessionId: 11, revision: 5, structured: { title: '模型' }, fieldSources: {}, elements: [] }); await flushPromises()
    expect(await fieldValue(wrapper, titleField)).toBe('已保存手改')
  })
  it('手改要素立即落库并带播报标志，新建未落库草稿保持本地不触发保存', async () => {
    route.query = { draftId: 1 }; mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11 }) })
    const wrapper = createWrapper(); await flushPromises()
    await editField(wrapper, titleField, '手改标题')
    // 已有草稿：立即保存并请求服务端往会话写播报消息
    expect(mocks.updateDraft).toHaveBeenCalledWith(1, expect.objectContaining({ title: '手改标题', notifyChanges: true }))
    const fresh = createWrapper(); await flushPromises()
    await editField(fresh, titleField, '新建草稿的手改')
    // 新建草稿（无会话可播报）：不立即保存，待首次发送对话时统一持久化
    expect(mocks.createDraft).not.toHaveBeenCalled()
  })
})

describe('report 提交拦截文案（微需求快速通道）', () => {
  it('light 草稿提交被拦：显示轻量四项指引，不显示B区改判逃生口', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, title: '更换首页顶部logo', content: '把首页顶部logo换成新设计的蓝色版本',
      ext: { mode: { level: 'light' }, typeRecognition: { business: 0.9 } } }), quality: [], messages: [] })
    mocks.submitDemand.mockRejectedValueOnce(new ApiError(400, '验收标准未填写'))
    const wrapper = createWrapper(); await flushPromises()
    wrapper.findComponent(PanelStub).vm.$emit('submit'); await flushPromises()
    expect(wrapper.text()).toContain('轻量提报只需四项')
    expect(wrapper.text()).toContain('期望效果')
    // light 不问 B 区：即使判型为业务需求也不给改判逃生口
    expect(wrapper.text()).not.toContain('改判为用户需求或功能需求')
  })
  it('standard 业务草稿提交被拦：保留改判逃生口，不显示轻量指引', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, title: '晨会持仓报表', content: '客户经理每天晨会前查看各机构持仓',
      ext: { typeRecognition: { business: 0.9 } } }), quality: [], messages: [] })
    mocks.submitDemand.mockRejectedValueOnce(new ApiError(400, '业务目标未填写'))
    const wrapper = createWrapper(); await flushPromises()
    wrapper.findComponent(PanelStub).vm.$emit('submit'); await flushPromises()
    expect(wrapper.text()).toContain('改判为用户需求或功能需求')
    expect(wrapper.text()).not.toContain('轻量提报只需四项')
  })
})

describe('report 打回待补充（方案③ NEED_INFO）', () => {
  it('NEED_INFO 草稿进对话页补充：不跳详情；打回播报不参与质量回放', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({
      demand: demand(1, { status: 'NEED_INFO', sessionId: 11, revision: 5, ext: { returnReason: { reason: '还缺紧急程度', returnedBy: '李整理' } } }),
      quality: [],
      messages: [
        { id: 1, role: 'ASSISTANT', structuredPayload: JSON.stringify({ demandId: 1, sessionId: 11, revision: 5, elements: [{ key: 'businessScenario', status: 'OK', label: '业务场景', note: '', attempts: 0 }] }) },
        { id: 2, role: 'ASSISTANT', content: '这条需求被整理人员打回了，需要补充信息后重新提交。', structuredPayload: JSON.stringify({ kind: 'returnNotice', reason: '还缺紧急程度' }) },
      ]
    })
    const wrapper = createWrapper(); await flushPromises()
    expect(router.replace).not.toHaveBeenCalledWith('/demand/1')
    expect(wrapper.findComponent(PanelStub).props('demandId')).toBe(1)
    // 尾部打回播报被排除，质量清单从更早的对话结果消息恢复
    expect(wrapper.findComponent(PanelStub).props('quality')).toHaveLength(1)
  })
  it('SUBMITTED 需求进入则跳转详情页', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { status: 'SUBMITTED' }), quality: [], messages: [] })
    const wrapper = createWrapper(); await flushPromises()
    expect(router.replace).toHaveBeenCalledWith('/demand/1')
  })
  it('NEED_INFO 重提确认弹窗用打回话术；普通草稿仍用常规话术', async () => {
    route.query = { draftId: 1 }
    mocks.getDemand.mockResolvedValue({ demand: demand(1, { status: 'NEED_INFO', sessionId: 11, title: '更换首页顶部logo', content: '把首页顶部logo换成新设计的蓝色版本' }), quality: [], messages: [] })
    mocks.submitDemand.mockResolvedValue(demand(1, { status: 'SUBMITTED', demandNo: 'TECH-20261011-004' }))
    const wrapper = createWrapper(); await flushPromises()
    wrapper.findComponent(PanelStub).vm.$emit('submit'); await flushPromises()
    expect(showConfirmDialog).toHaveBeenCalledWith(expect.objectContaining({ title: '重新提交', message: expect.stringContaining('这条需求此前被打回过') }))
    expect(mocks.submitDemand).toHaveBeenCalledWith(1, 1)

    mocks.getDemand.mockResolvedValue({ demand: demand(1, { sessionId: 11, title: '海报生成智能体', content: '我要做个海报生成智能体，给市场部用' }), quality: [], messages: [] })
    const draft = createWrapper(); await flushPromises()
    draft.findComponent(PanelStub).vm.$emit('submit'); await flushPromises()
    expect(showConfirmDialog).toHaveBeenLastCalledWith(expect.objectContaining({ title: '确认提交', message: expect.stringContaining('请确认要素内容准确') }))
  })
})
