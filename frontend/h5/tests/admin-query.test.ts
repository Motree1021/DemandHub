import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import Vant from 'vant'
import Admin from '@/views/admin/index.vue'
import { adminDemands, downloadXlsx, myDemands } from '@/api/demand'
const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), downloadFile: vi.fn() }))
vi.mock('@/api/request', () => mocks)
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
const FieldStub = defineComponent({ props: ['field', 'modelValue'], emits: ['update:modelValue'], template: '<input :data-field="field.key" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' })
const wrappers: VueWrapper[] = []
beforeEach(() => {
  vi.clearAllMocks()
  mocks.get.mockImplementation(async path => path === '/standards' ? [{ code: 'TECH', name: '科技需求' }] : { records: [], total: 0, current: 1, size: 20, pages: 0 })
})
afterEach(() => wrappers.splice(0).forEach(wrapper => wrapper.unmount()))
describe('列表和导出共用非空筛选', () => {
  it('默认全部与我的需求不发送空Literal/date参数', async () => {
    await adminDemands({ page: 1, size: 20, type: '', status: '', from: '', to: '' })
    expect(mocks.get).toHaveBeenLastCalledWith('/admin/demand/list', { page: 1, size: 20 })
    await myDemands({ page: 1, size: 15, status: '' })
    expect(mocks.get).toHaveBeenLastCalledWith('/demand/my', { page: 1, size: 15 })
  })
  it('筛选字段保持列表与XLSX一致，仅列表额外分页', async () => {
    const filters = { type: 'TECH', status: '', from: '2026-09-01', to: '2026-09-30' }
    await adminDemands({ ...filters, page: 1, size: 20 }); await downloadXlsx(filters)
    const listed = mocks.get.mock.calls.at(-1)![1]
    const downloaded = mocks.downloadFile.mock.calls.at(-1)![2]
    expect(downloaded).toEqual({ type: 'TECH', from: '2026-09-01', to: '2026-09-30' })
    expect(listed).toEqual({ ...downloaded, page: 1, size: 20 })
  })
  it('管理员页面首次加载默认全部、筛选、重置都可查询', async () => {
    const wrapper = mount(Admin, { global: { plugins: [Vant], stubs: { AppLayout: { template: '<div><slot /></div>' }, StandardField: FieldStub } } }); wrappers.push(wrapper); await flushPromises()
    expect(mocks.get).toHaveBeenLastCalledWith('/admin/demand/list', { page: 1, size: 20 })
    await wrapper.find('[data-field="type"]').setValue('TECH')
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click'); await flushPromises()
    expect(mocks.get).toHaveBeenLastCalledWith('/admin/demand/list', { type: 'TECH', page: 1, size: 20 })
    await wrapper.findAll('button').find(button => button.text() === '重置')!.trigger('click'); await flushPromises()
    expect(mocks.get).toHaveBeenLastCalledWith('/admin/demand/list', { page: 1, size: 20 })
    await wrapper.findAll('button').find(button => button.text() === '导出 XLSX')!.trigger('click'); await flushPromises()
    expect(mocks.downloadFile).toHaveBeenCalledWith('/admin/demand/export.xlsx', 'demandhub.xlsx', {})
  })
})
