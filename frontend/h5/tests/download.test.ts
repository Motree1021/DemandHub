import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { downloadFile, TOKEN_KEY } from '@/api/request'
import { guideChatStream } from '@/api/agent'
import type { GuideRequest } from '@/api/sse'
function response(type: string, status = 200, json: unknown = null) {
  return { ok: status < 400, status, headers: new Headers({ 'content-type': type, 'content-disposition': "attachment; filename*=UTF-8''%E9%9C%80%E6%B1%82.xlsx" }), json: vi.fn().mockResolvedValue(json), blob: vi.fn().mockResolvedValue(new Blob(['content'])) }
}
let fetchMock: ReturnType<typeof vi.fn>
const createObjectURL = vi.fn(); const revokeObjectURL = vi.fn()
beforeEach(() => {
  vi.useFakeTimers(); fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('URL', { createObjectURL: createObjectURL.mockReset().mockReturnValue('blob:download'), revokeObjectURL: revokeObjectURL.mockReset() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  localStorage.setItem(TOKEN_KEY, 'test-bearer')
})
afterEach(() => { vi.runAllTimers(); vi.useRealTimers() })
describe('Bearer下载与SSE请求', () => {
  it('xlsx带Bearer与日期筛选，使用服务文件名并释放Blob URL', async () => {
    fetchMock.mockResolvedValue(response('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click')
    await downloadFile('/admin/demand/export.xlsx', 'fallback.xlsx', { from: '2026-09-01', to: '2026-09-30' })
    expect(fetchMock).toHaveBeenCalledWith('/demandhub-api/admin/demand/export.xlsx?from=2026-09-01&to=2026-09-30', { headers: { Authorization: 'Bearer test-bearer' } })
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe('需求.xlsx')
    expect(document.querySelector('a')).toBeNull()
    vi.runAllTimers(); expect(revokeObjectURL).toHaveBeenCalledWith('blob:download')
  })
  it('markdown同样通过认证fetch下载', async () => {
    fetchMock.mockResolvedValue(response('text/markdown; charset=utf-8'))
    await downloadFile('/demand/1/export.md', 'draft-1.md')
    expect(fetchMock).toHaveBeenCalledWith('/demandhub-api/demand/1/export.md', { headers: { Authorization: 'Bearer test-bearer' } })
  })
  it('HTTP200业务错误JSON不作为文件成功', async () => {
    fetchMock.mockResolvedValue(response('application/json', 200, { code: 403, message: '无权限' }))
    await expect(downloadFile('/admin/demand/export.xlsx', 'fallback.xlsx')).rejects.toMatchObject({ code: 403, message: '无权限' })
    expect(createObjectURL).not.toHaveBeenCalled()
  })
  it('401清token发出重新登录事件，单次请求不重试', async () => {
    const unauthorized = vi.fn(); window.addEventListener('demandhub:unauthorized', unauthorized, { once: true })
    fetchMock.mockResolvedValue(response('application/json', 401, { code: 401, message: '登录已过期' }))
    await expect(downloadFile('/demand/1/export.md', 'draft-1.md')).rejects.toMatchObject({ code: 401 })
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull(); expect(unauthorized).toHaveBeenCalledOnce(); expect(fetchMock).toHaveBeenCalledOnce()
  })
  it('聊天只发送冻结DTO，不发送游离formContext/sources，Bearer一致', async () => {
    const request: GuideRequest = { demandId: 1, sessionId: 11, requestId: 'turn-1', revision: 2, message: '需求' }
    fetchMock.mockResolvedValue(response('application/json', 200, { code: 1401, message: 'AI 暂不可用' }))
    await expect(guideChatStream(request, {})).rejects.toMatchObject({ code: 1401 })
    expect(fetchMock).toHaveBeenCalledWith('/demandhub-api/agent/guide/chat/stream', expect.objectContaining({ method: 'POST', body: JSON.stringify(request), headers: { 'Content-Type': 'application/json', Authorization: 'Bearer test-bearer' } }))
  })
})
