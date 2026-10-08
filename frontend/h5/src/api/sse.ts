import type { DemandForm, ElementStatus, FieldSources, TypeRecognition } from './demand'
export interface GuideRequest { demandId: number; sessionId: number; requestId: string; revision: number; message: string }
export interface GranularityHint { level: 'too_broad' | 'too_narrow'; hint: string; converge: string }
export interface GuidePayload {
  demandId: number; sessionId: number; requestId: string; revision: number
  structured: Omit<DemandForm, 'fieldSources'>; fieldSources: FieldSources; missing: string[]; elements: ElementStatus[]
  askedTarget: string | null; canSubmit: boolean; guidanceComplete: boolean; qualityComplete: boolean; ready: boolean; quickReplies: string[]
  typeRecognition?: TypeRecognition | null; granularityHint?: GranularityHint | null; impactHints?: string[]
}
export class StreamError extends Error {
  constructor(public code: number, message: string) { super(message); this.name = 'StreamError' }
}
export interface StreamHandlers { onDelta?: (delta: string) => void; onProcessing?: () => void }
function parse(data: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(data)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error()
    return parsed
  } catch { throw new StreamError(-1, 'AI 响应格式错误，请重试') }
}
function validatePayload(data: Record<string, unknown>, request: GuideRequest): GuidePayload {
  const structured = data.structured as Record<string, unknown> | null
  if (data.requestId !== request.requestId || data.demandId !== request.demandId || data.sessionId !== request.sessionId ||
      !Number.isInteger(data.revision) || Number(data.revision) <= request.revision ||
      !structured || typeof structured !== 'object' || !structured.ext || typeof structured.ext !== 'object' || Array.isArray(structured.ext) ||
      (structured.elements !== undefined && (typeof structured.elements !== 'object' || structured.elements === null || Array.isArray(structured.elements))) ||
      !['title', 'demandTypeCode', 'content', 'urgency', 'expectDeliveryAt'].every(key => key in structured) ||
      !['title', 'content'].every(key => structured[key] === null || typeof structured[key] === 'string') ||
      ![null, 'TECH', 'MATL', 'TRAIN'].includes(structured.demandTypeCode as string | null) ||
      ![null, 'NORMAL', 'URGENT', 'CRITICAL'].includes(structured.urgency as string | null) ||
      !(structured.expectDeliveryAt === null || (typeof structured.expectDeliveryAt === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(structured.expectDeliveryAt))) ||
      !data.fieldSources || typeof data.fieldSources !== 'object' || Array.isArray(data.fieldSources) ||
      !Object.values(data.fieldSources).every(source => ['default', 'agent', 'user'].includes(String(source))) ||
      !Array.isArray(data.elements) || !data.elements.every(element => element && typeof element.key === 'string' && ['OK', 'VAGUE', 'MISSING', 'SKIP'].includes(element.status)) ||
      !Array.isArray(data.missing) || !data.missing.every(value => typeof value === 'string') ||
      !Array.isArray(data.quickReplies) || !data.quickReplies.every(value => typeof value === 'string') ||
      !['canSubmit', 'guidanceComplete', 'qualityComplete'].every(key => typeof data[key] === 'boolean')) {
    throw new StreamError(-1, 'AI 响应与当前草稿不匹配，请重试')
  }
  return data as unknown as GuidePayload
}
/** 只有 structured 和匹配的 completed done 才成功；EOF/错误不会产生成功结果。 */
export async function consumeGuideStream(body: ReadableStream<Uint8Array>, request: GuideRequest, handlers: StreamHandlers = {}): Promise<GuidePayload> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result: GuidePayload | null = null
  try {
    for (;;) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      buffer = buffer.replace(/\r\n/g, '\n').replace(done ? /\r/g : /\r(?!$)/g, '\n')
      let index: number
      while ((index = buffer.indexOf('\n\n')) >= 0) {
        const block = buffer.slice(0, index)
        buffer = buffer.slice(index + 2)
        let event = 'message'
        const lines: string[] = []
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) lines.push(line.slice(5).replace(/^ /, ''))
        }
        if (!lines.length) continue // 注释/心跳
        const data = parse(lines.join('\n'))
        if (event === 'error') throw new StreamError(typeof data.code === 'number' ? data.code : -1, typeof data.message === 'string' ? data.message : 'AI 请求未完成')
        if (event === 'processing') {
          if (data.requestId !== request.requestId || data.status !== 'processing') throw new StreamError(-1, 'AI 处理状态不匹配')
          handlers.onProcessing?.()
        } else if (event === 'message') {
          if (typeof data.delta !== 'string') throw new StreamError(-1, 'AI 文本响应格式错误')
          handlers.onDelta?.(data.delta)
        } else if (event === 'structured') {
          if (result) throw new StreamError(-1, 'AI 返回了重复结果')
          result = validatePayload(data, request)
        } else if (event === 'done') {
          if (!result || data.requestId !== request.requestId || data.status !== 'completed') throw new StreamError(-1, 'AI 完成状态不匹配，请重试')
          return result
        }
      }
      if (done) throw new StreamError(-1, '连接已中断，结果尚未确认，请重试')
    }
  } finally {
    // 成功后无需等待 EOF；失败/取消同样关闭网络读取资源。
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
