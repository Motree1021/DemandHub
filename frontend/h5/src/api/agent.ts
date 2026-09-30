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

/** P10：要素质量状态（rubric 四态） */
export interface ElementStatus {
  key: string
  status: 'OK' | 'VAGUE' | 'MISSING' | 'SKIP'
  note: string
  attempts: number
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
  const token = localStorage.getItem('demandhub_h5_token')
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
      // 会话失效：与 request.ts 一致，重载页面走静默授权
      window.location.reload()
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
