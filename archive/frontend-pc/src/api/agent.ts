import { get, post, API_BASE } from './request'

/** Agent 会话 */
export interface AgentSession {
  id: number
  sessionNo: string
  userId: number
  scene: 'SUBMIT_GUIDE' | 'HANDLE_ASSIST'
  demandId: number | null
  title: string
  status: string
  createdAt: string
  updatedAt: string
}

export interface AgentMessage {
  id: number
  sessionId: number
  role: 'USER' | 'ASSISTANT' | 'SYSTEM'
  content: string
  structuredPayload: string | null
  createdAt: string
}

export function createAgentSession(scene: string, demandId?: number, firstMessage?: string): Promise<AgentSession> {
  return post('/agent/session', { scene, demandId, firstMessage })
}

export function listAgentSessions(scene?: string): Promise<AgentSession[]> {
  return get('/agent/session/list', scene ? { scene } : {})
}

export function agentSessionMessages(sessionId: number): Promise<AgentMessage[]> {
  return get(`/agent/session/${sessionId}/messages`)
}

export function closeAgentSession(sessionId: number): Promise<void> {
  return post(`/agent/session/${sessionId}/close`)
}

/* ---------------- 提报启发 ---------------- */

/** AI 结构化回填字段 */
export interface GuideStructured {
  title?: string
  demandTypeCode?: string
  content?: string
  urgency?: string
  expectDeliveryAt?: string
  ext?: Record<string, unknown>
}

export interface GuideResult {
  reply: string
  structured: GuideStructured
  missing: string[]
  ready: boolean
}

/** P10：要素质量状态（rubric 四态） */
export interface ElementStatus {
  key: string
  status: 'OK' | 'VAGUE' | 'MISSING' | 'SKIP'
  note: string
  attempts: number
}

/** 一次性对话（非流式，调试用） */
export function guideChat(sessionId: number, message: string, formContext?: Record<string, unknown>): Promise<GuideResult> {
  return post('/agent/guide/chat', { sessionId, message, formContext })
}

export class AgentUnavailableError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

/**
 * SSE 流式对话（fetch + ReadableStream 手工解析；EventSource 不支持 POST/自定义请求头）。
 * 大模型不可用时后端同步返回统一 JSON（code=1401），此处抛 AgentUnavailableError 供前端降级。
 */
export async function guideChatStream(
  sessionId: number,
  message: string,
  formContext: Record<string, unknown> | undefined,
  handlers: {
    onDelta: (delta: string) => void
    onStructured: (payload: {
      structured: GuideStructured
      missing: string[]
      ready: boolean
      elements?: ElementStatus[]
      quickReplies?: string[]
    }) => void
  }
): Promise<void> {
  const token = localStorage.getItem('demandhub_token')
  const resp = await fetch(`${API_BASE}/agent/guide/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ sessionId, message, formContext })
  })
  const contentType = resp.headers.get('content-type') || ''
  if (!resp.ok || !contentType.includes('text/event-stream')) {
    const data = (await resp.json().catch(() => null)) as { code?: number; message?: string } | null
    if (resp.status === 401 || data?.code === 401) {
      window.location.href = `${import.meta.env.BASE_URL}login`
      throw new AgentUnavailableError(401, '登录已过期')
    }
    throw new AgentUnavailableError(data?.code ?? -1, data?.message || 'AI 服务暂不可用，请稍后再试')
  }
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let currentEvent = 'message'
  for (;;) {
    const { done, value } = await reader.read()
    if (done) {
      break
    }
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const dataLines: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event:')) {
          currentEvent = line.slice(6).trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart())
        }
      }
      const dataStr = dataLines.join('\n')
      if (!dataStr) {
        continue
      }
      if (currentEvent === 'message') {
        try {
          handlers.onDelta((JSON.parse(dataStr) as { delta?: string }).delta ?? '')
        } catch {
          /* 忽略解析失败的分片 */
        }
      } else if (currentEvent === 'structured') {
        try {
          handlers.onStructured(JSON.parse(dataStr) as {
            structured: GuideStructured
            missing: string[]
            ready: boolean
            elements?: ElementStatus[]
            quickReplies?: string[]
          })
        } catch {
          /* 忽略解析失败的结构化事件 */
        }
      }
      currentEvent = 'message'
    }
  }
}

/* ---------------- 处理辅助 ---------------- */

export interface AgentDraft {
  id: number
  demandId: number
  sessionId: number | null
  draftType: 'QUESTIONS' | 'SOLUTION'
  content: string
  status: 'PENDING' | 'CONFIRMED' | 'DISCARDED'
  confirmedBy: number | null
  confirmedAt: string | null
  targetSolutionId: number | null
  createdBy: number
  createdAt: string
  updatedAt: string
}

export function assistQuestions(sessionId: number): Promise<AgentDraft> {
  return post('/agent/assist/questions', { sessionId })
}

export function assistSolution(sessionId: number): Promise<AgentDraft> {
  return post('/agent/assist/solution', { sessionId })
}

export function assistDrafts(demandId: number): Promise<AgentDraft[]> {
  return get('/agent/assist/drafts', { demandId })
}

export function confirmSolutionDraft(
  draftId: number,
  data: { specContent?: string; solutionContent?: string; planDeliveryAt?: string }
): Promise<AgentDraft> {
  return post(`/agent/assist/drafts/${draftId}/confirm`, data)
}

export function discardDraft(draftId: number): Promise<void> {
  return post(`/agent/assist/drafts/${draftId}/discard`)
}

/* ---------------- RAG 相似需求 ---------------- */

export interface SimilarDoc {
  demandId: number
  demandNo: string
  title: string
  demandTypeCode: string
  score: number
}

export function similarDemands(demandId: number, topN = 5): Promise<SimilarDoc[]> {
  return get('/agent/rag/similar', { demandId, topN })
}
