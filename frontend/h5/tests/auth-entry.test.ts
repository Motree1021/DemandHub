import { describe, expect, it } from 'vitest'
import { cleanTicketUrl, readTicketEntry } from '@/utils/auth-entry'
describe('hash 路由渠道票据', () => {
  it('读取外层票据并保留hash详情与无关query', () => {
    const url = new URL('https://example.test/h5-preview/any/?ticket=outer&from=chuangjinls&state=a&theme=light#/report?draftId=5')
    expect(readTicketEntry(url)).toEqual({ ticket: 'outer', from: 'chuangjinls', state: 'a' })
    expect(cleanTicketUrl(url)).toBe('/h5-preview/any/?theme=light#/report?draftId=5')
  })
  it('兼容hash query，外层优先，同时清理两处', () => {
    const url = new URL('https://example.test/h5/other/?ticket=outer#/report?ticket=inner&from=chuangjinls&state=a&draftId=5')
    expect(readTicketEntry(url)?.ticket).toBe('outer')
    expect(cleanTicketUrl(url)).toBe('/h5/other/#/report?draftId=5')
  })
  it('无票据不采信URL身份', () => { expect(readTicketEntry(new URL('https://example.test/?name=admin&userid=1#/report'))).toBeNull() })
})
