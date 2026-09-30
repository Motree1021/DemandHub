import { get, post, API_BASE, bearerHeaders, expireSession } from './request'
import { consumeGuideStream, StreamError, type GuideRequest, type GuidePayload, type StreamHandlers } from './sse'
export type { GuideRequest, GuidePayload } from './sse'
export { StreamError } from './sse'
export type { ElementStatus, AgentMessage } from './demand'
export interface AgentSession { id: number; demandId: number; scene: string; status: string; askedTarget?: string | null }
export const createAgentSession = (demandId: number): Promise<AgentSession> => post('/agent/session', { demandId, scene: 'SUBMIT_GUIDE' })
export const agentSessionMessages = (sessionId: number) => get<import('./demand').AgentMessage[]>(`/agent/session/${sessionId}/messages`)
export async function guideChatStream(request: GuideRequest, handlers: StreamHandlers, signal?: AbortSignal): Promise<GuidePayload> {
  const response = await fetch(`${API_BASE}/agent/guide/chat/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...bearerHeaders() }, body: JSON.stringify(request), signal
  })
  if (!response.ok || !(response.headers.get('content-type') || '').includes('text/event-stream')) {
    const result = await response.json().catch(() => null) as { code?: number; message?: string } | null
    const code = result?.code || response.status
    if (code === 401) expireSession()
    throw new StreamError(code, result?.message || 'AI 服务暂不可用，请稍后重试')
  }
  if (!response.body) throw new StreamError(-1, 'AI 未返回响应')
  try { return await consumeGuideStream(response.body, request, handlers) }
  catch (error) { if (error instanceof StreamError && error.code === 401) expireSession(); throw error }
}
