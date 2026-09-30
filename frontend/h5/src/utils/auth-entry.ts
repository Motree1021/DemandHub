import type { ChannelParameters } from '@/api/auth'

export const CHANNEL_ENTRY_KEYS = ['ticket', 'from', 'state', 'userid', 'X-Auth-Token', 'userName', 'department'] as const
const PARAMETER_KEYS = ['userid', 'X-Auth-Token', 'userName', 'department'] as const
export interface TicketEntry { ticket: string; from: string; state?: string }
export type ChannelEntry =
  | { kind: 'ticket'; parameters: TicketEntry }
  | { kind: 'parameters'; parameters: ChannelParameters }
  | { kind: 'invalid'; message: string }

function hashParts(url: URL): [string, URLSearchParams] {
  const index = url.hash.indexOf('?')
  return index < 0 ? [url.hash, new URLSearchParams()] : [url.hash.slice(0, index), new URLSearchParams(url.hash.slice(index + 1))]
}
/** has覆盖空值和只出现部门的入口；任何歧义均拒绝，绝不依靠单独userid登录。 */
export function readChannelEntry(url: URL): ChannelEntry | null {
  const outer = url.searchParams
  const [, inner] = hashParts(url)
  for (const key of CHANNEL_ENTRY_KEYS) {
    if (outer.getAll(key).length > 1 || inner.getAll(key).length > 1) {
      return { kind: 'invalid', message: '登录入口参数重复，请从创金零售重新进入' }
    }
    if (outer.has(key) && inner.has(key)) {
      return { kind: 'invalid', message: outer.get(key) !== inner.get(key)
        ? '登录入口参数冲突，请从创金零售重新进入'
        : '登录入口参数重复，请从创金零售重新进入' }
    }
  }
  if (CHANNEL_ENTRY_KEYS.some(key => outer.has(key)) && CHANNEL_ENTRY_KEYS.some(key => inner.has(key))) {
    return { kind: 'invalid', message: '登录入口参数跨位置混合，请从创金零售重新进入' }
  }
  const has = (key: string) => outer.has(key) || inner.has(key)
  const get = (key: string) => outer.get(key) ?? inner.get(key) ?? ''
  const hasParameters = PARAMETER_KEYS.some(has)
  if (has('ticket') && hasParameters) return { kind: 'invalid', message: '登录入口身份不明确，请从创金零售重新进入' }
  if (hasParameters) {
    const userid = get('userid').trim()
    const authToken = get('X-Auth-Token')
    const userName = get('userName').trim()
    const department = get('department').trim()
    if (!userid || !authToken.trim() || !userName) return { kind: 'invalid', message: '登录参数不完整，请从创金零售重新进入' }
    if (userid.length > 64 || authToken.length > 4096 || userName.length > 64 || department.length > 128) {
      return { kind: 'invalid', message: '登录参数格式无效，请从创金零售重新进入' }
    }
    return { kind: 'parameters', parameters: { userid, authToken, userName, ...(department ? { department } : {}) } }
  }
  if (has('ticket')) {
    const ticket = get('ticket')
    if (!ticket.trim()) return { kind: 'invalid', message: '登录票据无效，请从创金零售重新进入' }
    return { kind: 'ticket', parameters: { ticket, from: get('from') || 'chuangjinls', state: get('state') || undefined } }
  }
  return null
}
export function cleanChannelUrl(url: URL): string {
  const [path, inner] = hashParts(url)
  CHANNEL_ENTRY_KEYS.forEach(key => { url.searchParams.delete(key); inner.delete(key) })
  url.hash = path + (inner.size ? `?${inner}` : '')
  return url.pathname + url.search + url.hash
}
export function cleanChannelQuery<T extends Record<string, unknown>>(query: T): T {
  const cleaned = { ...query }
  CHANNEL_ENTRY_KEYS.forEach(key => delete cleaned[key])
  return cleaned
}
// 保留原ticket工具入口；现在遵守统一歧义拒绝规则。
export function readTicketEntry(url: URL): TicketEntry | null {
  const entry = readChannelEntry(url)
  return entry?.kind === 'ticket' ? entry.parameters : null
}
export const cleanTicketUrl = cleanChannelUrl

/** 仅保留Vue Router需要的历史字段，旧current/back/forward也同步去掉入口参数。 */
export function cleanChannelHistoryState(state: unknown): Record<string, unknown> | null {
  if (!state || typeof state !== 'object') return null
  const source = state as Record<string, unknown>
  const cleaned: Record<string, unknown> = {}
  for (const key of ['back', 'current', 'forward']) {
    if (typeof source[key] === 'string') {
      const url = new URL('https://entry.invalid/')
      url.hash = source[key] as string
      cleanChannelUrl(url)
      cleaned[key] = url.hash.slice(1)
    } else if (source[key] === null) cleaned[key] = null
  }
  if (typeof source.position === 'number' && Number.isFinite(source.position)) cleaned.position = source.position
  if (typeof source.replaced === 'boolean') cleaned.replaced = source.replaced
  if (source.scroll && typeof source.scroll === 'object') {
    const scroll = source.scroll as Record<string, unknown>
    if (typeof scroll.left === 'number' && typeof scroll.top === 'number') cleaned.scroll = { left: scroll.left, top: scroll.top }
  } else if (source.scroll === null) cleaned.scroll = null
  return cleaned
}
