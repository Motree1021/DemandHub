import { describe, expect, it, vi } from 'vitest'
import { consumeGuideStream, type GuidePayload, type GuideRequest } from '@/api/sse'
const request: GuideRequest = { demandId: 1, sessionId: 2, requestId: 'turn-1', revision: 3, message: '做个报表' }
const payload: GuidePayload = { demandId: 1, sessionId: 2, requestId: 'turn-1', revision: 4, structured: { title: '报表', demandTypeCode: 'TECH', content: '需求描述', urgency: 'NORMAL', expectDeliveryAt: null, ext: {} }, fieldSources: {}, elements: [], missing: [], askedTarget: null, canSubmit: true, guidanceComplete: true, qualityComplete: false, ready: true, quickReplies: [] }
const event = (name: string, data: unknown) => `event: ${name}\ndata: ${typeof data === 'string' ? data : JSON.stringify(data)}\n\n`
const success = () => event('message', { delta: '已整理' }) + event('structured', payload) + event('done', { requestId: 'turn-1', status: 'completed' })
function stream(text: string, chunkSize = 10) {
  const encoded = new TextEncoder().encode(text)
  return new ReadableStream<Uint8Array>({ start(controller) { for (let i = 0; i < encoded.length; i += chunkSize) controller.enqueue(encoded.slice(i, i + chunkSize)); controller.close() } })
}
describe('SSE 成功终态', () => {
  it('UTF8任意切分、CRLF、心跳与processing，完成后才返回完整结果', async () => {
    const onDelta = vi.fn(); const onProcessing = vi.fn()
    const text = ': heartbeat\n\n' + event('processing', { requestId: 'turn-1', status: 'processing' }) + success()
    const result = await consumeGuideStream(stream(text.replace(/\n/g, '\r\n'), 1), request, { onDelta, onProcessing })
    expect(result).toEqual(payload); expect(onDelta).toHaveBeenCalledWith('已整理'); expect(onProcessing).toHaveBeenCalledOnce()
  })
  it.each([
    ['EOF缺done', event('structured', payload)],
    ['空done', event('structured', payload) + 'event: done\ndata:\n\n'],
    ['done请求不匹配', event('structured', payload) + event('done', { requestId: 'other', status: 'completed' })],
    ['done状态不匹配', event('structured', payload) + event('done', { requestId: 'turn-1', status: 'failed' })],
    ['done前无structured', event('done', { requestId: 'turn-1', status: 'completed' })],
    ['structured无完整草稿', event('structured', { ...payload, structured: { title: '缺其他字段' } }) + event('done', { requestId: 'turn-1', status: 'completed' })],
    ['structured错误草稿', event('structured', { ...payload, demandId: 99 })],
    ['structured旧revision', event('structured', { ...payload, revision: 3 })],
    ['格式错误', event('message', '{not-json')],
    ['重复structured', event('structured', payload) + event('structured', payload)]
  ])('%s不能假成功', async (_name, text) => { await expect(consumeGuideStream(stream(text), request)).rejects.toThrow() })
  it('流内error忽略伪done，抛原业务码', async () => {
    const text = event('structured', payload) + event('error', { requestId: 'turn-1', code: 409, message: '草稿已更新' }) + event('done', { requestId: 'turn-1', status: 'completed' })
    await expect(consumeGuideStream(stream(text), request)).rejects.toMatchObject({ code: 409, message: '草稿已更新' })
  })
  it('读取取消/断线不成功且释放reader', async () => {
    const body = new ReadableStream<Uint8Array>({ start(controller) { controller.error(new DOMException('请求已取消', 'AbortError')) } })
    await expect(consumeGuideStream(body, request)).rejects.toMatchObject({ name: 'AbortError' })
    expect(body.locked).toBe(false)
  })
})
