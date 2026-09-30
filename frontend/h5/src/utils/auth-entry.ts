const ONE_TIME_KEYS = ['ticket', 'from', 'state']
export interface TicketEntry { ticket: string; from: string; state?: string }
/** 外层查询参数优先，兼容宿主把参数放在 hash 路由后的形式。 */
export function readTicketEntry(url: URL): TicketEntry | null {
  const hashQuery = new URLSearchParams(url.hash.split('?')[1] || '')
  const get = (key: string) => url.searchParams.get(key) || hashQuery.get(key) || ''
  const ticket = get('ticket')
  return ticket ? { ticket, from: get('from') || 'chuangjinls', state: get('state') || undefined } : null
}
export function cleanTicketUrl(url: URL): string {
  ONE_TIME_KEYS.forEach(key => url.searchParams.delete(key))
  const [path, query = ''] = url.hash.split('?')
  const hashQuery = new URLSearchParams(query)
  ONE_TIME_KEYS.forEach(key => hashQuery.delete(key))
  url.hash = path + (hashQuery.size ? `?${hashQuery}` : '')
  return url.pathname + url.search + url.hash
}
