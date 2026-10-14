// @vitest-environment jsdom
/** P4 报表导出页：任务列表状态渲染 / 下载仅 SUCCESS 可见 / 导出参数拼装（日期排他右边界 +1 天）。 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

beforeAll(() => {
  // jsdom 26 自带 matchMedia 占位（调用返回 undefined），必须无条件覆盖
  window.matchMedia = ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {} unobserve() {} disconnect() {}
    } as unknown as typeof ResizeObserver
  }
})

const mocks = vi.hoisted(() => ({
  export: vi.fn(), tasks: vi.fn(), downloadFile: vi.fn(),
}))
vi.mock('@/api', () => ({
  reportApi: {
    export: mocks.export,
    tasks: mocks.tasks,
    downloadPath: (id: number) => `/report/download/${id}`,
  },
}))
vi.mock('@/api/request', () => ({ downloadFile: mocks.downloadFile }))

import ReportTasks from '../src/views/report/ReportTasks.vue'

const TASKS = [
  { id: 2, taskNo: 'RPT-20261014-002', reportType: 'DEMAND_LIST', status: 'SUCCESS',
    fileName: '需求清单-RPT-20261014-002.xlsx', errorMsg: null,
    createdAt: '2026-10-14 10:00:00', finishedAt: '2026-10-14 10:00:05' },
  { id: 1, taskNo: 'RPT-20261014-001', reportType: 'DEMAND_LIST', status: 'RUNNING',
    fileName: null, errorMsg: null, createdAt: '2026-10-14 09:00:00', finishedAt: null },
]

function mountPage() {
  return mount(ReportTasks, { global: { plugins: [ElementPlus] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.tasks.mockResolvedValue({ records: TASKS, total: 2, size: 10, current: 1, pages: 1 })
  mocks.export.mockResolvedValue({ id: 3, taskNo: 'RPT-20261014-003' })
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('报表导出页', () => {
  it('渲染任务状态，下载按钮仅 SUCCESS 行可见且调下载', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('RPT-20261014-002')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('生成中')
    const downloadButtons = wrapper.findAll('button').filter(b => b.text() === '下载')
    expect(downloadButtons).toHaveLength(1)
    await downloadButtons[0].trigger('click')
    expect(mocks.downloadFile).toHaveBeenCalledWith(
      '/report/download/2', '需求清单-RPT-20261014-002.xlsx')
  })

  it('新建导出：关键字与 mine 透传，空值剔除', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll('button').find(b => b.text() === '新建导出')!.trigger('click')
    await flushPromises()
    // el-dialog 默认渲染在组件树内（不 append-to-body）
    const keyword = wrapper.find('.el-dialog .el-input input')
    ;(keyword.element as HTMLInputElement).value = '夹具'
    await keyword.trigger('input')
    await wrapper.find('.el-dialog .el-checkbox input').setValue(true)
    await wrapper.findAll('.el-dialog button').find(b => b.text() === '开始导出')!.trigger('click')
    await flushPromises()
    expect(mocks.export).toHaveBeenCalledWith(expect.objectContaining({
      keyword: '夹具',
      mine: true,
      status: undefined,
      demandTypeCode: undefined,
      submittedFrom: undefined,
      submittedTo: undefined,
    }))
  })

  it('toExportParams：结束日期 +1 天（后端排他右边界）', async () => {
    const { toExportParams } = await import('../src/views/report/ReportTasks.vue')
    expect(toExportParams({
      status: '', demandTypeCode: '', urgency: '', keyword: '',
      dates: ['2026-10-01', '2026-10-14'], mine: false,
    })).toEqual({
      status: undefined, demandTypeCode: undefined, urgency: undefined, keyword: undefined,
      submittedFrom: '2026-10-01', submittedTo: '2026-10-15', mine: undefined,
    })
  })
})
