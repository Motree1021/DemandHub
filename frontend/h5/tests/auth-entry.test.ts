import { describe, expect, it } from 'vitest'
import { cleanChannelHistoryState, cleanChannelQuery, cleanChannelUrl, readChannelEntry, readTicketEntry } from '@/utils/auth-entry'
const identity = 'userid=test-user&X-Auth-Token=synthetic-host-token&userName=%E6%B5%8B%E8%AF%95%E5%90%8D%E7%A7%B0'
describe('hash 路由渠道票据回归', () => {
  it('单一外层票据保留hash详情与无关query', () => {
    const url = new URL('https://example.test/h5-preview/any/?ticket=synthetic-ticket&from=chuangjinls&state=a&theme=light#/report?draftId=5')
    expect(readTicketEntry(url)).toEqual({ ticket: 'synthetic-ticket', from: 'chuangjinls', state: 'a' })
    expect(cleanChannelUrl(url)).toBe('/h5-preview/any/?theme=light#/report?draftId=5')
  })
  it('兼容单一hash ticket query', () => {
    const url = new URL('https://example.test/h5/other/#/report?ticket=synthetic-ticket&from=chuangjinls&state=a&draftId=5')
    expect(readTicketEntry(url)).toEqual({ ticket: 'synthetic-ticket', from: 'chuangjinls', state: 'a' })
    expect(cleanChannelUrl(url)).toBe('/h5/other/#/report?draftId=5')
  })
  it('不采信任意URL身份别名', () => { expect(readTicketEntry(new URL('https://example.test/?name=admin&user_id=1#/report'))).toBeNull() })
})
describe('宿主参数入口', () => {
  it('history只保留必要路由状态并清理前后路由及额外身份字段', () => {
    const state = cleanChannelHistoryState({ current: '/report?userid=test&X-Auth-Token=synthetic-host-token&userName=test&draftId=5', back: '/mine?X-Auth-Token=synthetic-host-token', forward: null, position: 3, replaced: true, scroll: { left: 0, top: 40 }, hostToken: 'synthetic-host-token' })
    expect(state).toEqual({ current: '/report?draftId=5', back: '/mine', forward: null, position: 3, replaced: true, scroll: { left: 0, top: 40 } })
    expect(JSON.stringify(state)).not.toContain('synthetic-host-token')
  })
  it('外层四参数映射JSON，组织可选，opaque token保留解码原值', () => {
    const url = new URL(`https://example.test/h5/any/?${identity}&department=%E9%9B%B6%E5%94%AE%E9%83%A8#/report?draftId=5`)
    expect(readChannelEntry(url)).toEqual({ kind: 'parameters', parameters: { userid: 'test-user', authToken: 'synthetic-host-token', userName: '测试名称', department: '零售部' } })
    expect(cleanChannelUrl(url)).toBe('/h5/any/#/report?draftId=5')
    const encoded = new URL('https://example.test/?userid=test-user&X-Auth-Token=synthetic%2Btoken%3D&userName=test#/mine')
    expect(readChannelEntry(encoded)).toMatchObject({ parameters: { authToken: 'synthetic+token=' } })
  })
  it('单一hash参数可读取，outer/hash分散身份必须拒绝', () => {
    const hash = new URL(`https://example.test/h5-preview/any/#/report?${identity}&draftId=5`)
    expect(readChannelEntry(hash)).toMatchObject({ kind: 'parameters', parameters: { userid: 'test-user' } })
    expect(cleanChannelUrl(hash)).toBe('/h5-preview/any/#/report?draftId=5')
    expect(readChannelEntry(new URL('https://example.test/?userid=test-user#/report?X-Auth-Token=synthetic-token&userName=test'))).toMatchObject({ kind: 'invalid' })
  })
  it.each([
    'userid=test-user', 'X-Auth-Token=synthetic-host-token', 'userName=test', 'department=test',
    'userid=test-user&X-Auth-Token=&userName=test', 'userid=test-user&X-Auth-Token=%20&userName=test',
    'userid=&X-Auth-Token=synthetic-host-token&userName=test', 'userid=test-user&X-Auth-Token=synthetic-host-token'
  ])('拒绝不完整形态并清理（%s）', query => {
    const url = new URL(`https://example.test/?${query}#/report?draftId=5`)
    expect(readChannelEntry(url)).toMatchObject({ kind: 'invalid', message: '登录参数不完整，请从创金零售重新进入' })
    expect(cleanChannelUrl(url)).toBe('/#/report?draftId=5')
  })
  it.each([
    `?${identity}&userid=test-user#/report`, `?${identity}#/report?userid=test-user`,
    `?${identity}#/report?userid=other-user`, `?${identity}&ticket=synthetic-ticket#/report`,
    `?ticket=synthetic-ticket#/report?${identity}`, '?ticket=synthetic-ticket&ticket=synthetic-ticket#/report',
    '?ticket=outer-synthetic#/report?ticket=inner-synthetic'
  ])('拒绝重复、冲突和混合身份并完整清理（%s）', query => {
    const url = new URL(`https://example.test/${query}`)
    expect(readChannelEntry(url)?.kind).toBe('invalid'); expect(cleanChannelUrl(url)).toBe('/#/report')
  })
  it('部门空值可省略，超长参数使用固定错误', () => {
    expect(readChannelEntry(new URL(`https://example.test/?${identity}&department=#/report`))).toMatchObject({ kind: 'parameters', parameters: { userid: 'test-user', userName: '测试名称' } })
    expect(readChannelEntry(new URL(`https://example.test/?${identity}&department=${'x'.repeat(129)}#/report`))).toMatchObject({ kind: 'invalid', message: '登录参数格式无效，请从创金零售重新进入' })
  })
  it('清路由query时移除所有身份字段，保留无关query', () => {
    expect(cleanChannelQuery({ userid: 'test-user', 'X-Auth-Token': 'synthetic-host-token', userName: 'test', department: 'test', ticket: 'synthetic-ticket', from: 'chuangjinls', state: 'a', draftId: '5', theme: ['light'] })).toEqual({ draftId: '5', theme: ['light'] })
  })
})
