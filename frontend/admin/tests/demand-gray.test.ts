/** 判型识别与置灰规则（utils/demand.ts）：confirmed 优先、置信度兜底、向下兼容置灰。 */
import { describe, expect, it } from 'vitest'
import { grayZones, recognitionLevel } from '../src/utils/demand'

describe('recognitionLevel 生效判型', () => {
  it('人工确认优先于置信度', () => {
    expect(recognitionLevel({ confirmed: 'user', business: 0.9, user: 0.1, function: 0 })).toBe('user')
  })
  it('无确认取置信度最高层', () => {
    expect(recognitionLevel({ business: 0.2, user: 0.7, function: 0.1 })).toBe('user')
    expect(recognitionLevel({ business: 0.8, user: 0.1, function: 0.1 })).toBe('business')
  })
  it('confirmed 为 null 时回落置信度', () => {
    expect(recognitionLevel({ confirmed: null, business: 0, user: 0, function: 0.6 })).toBe('function')
  })
  it('空值/全零/非法结构返回 null', () => {
    expect(recognitionLevel(null)).toBeNull()
    expect(recognitionLevel(undefined)).toBeNull()
    expect(recognitionLevel({})).toBeNull()
    expect(recognitionLevel({ business: 0, user: 0, function: 0 })).toBeNull()
    expect(recognitionLevel('business')).toBeNull()
  })
})

describe('grayZones 判型置灰（向下兼容）', () => {
  it('业务需求：全亮', () => {
    expect(grayZones({ confirmed: 'business' }).size).toBe(0)
  })
  it('用户需求：B 灰', () => {
    expect([...grayZones({ confirmed: 'user' })]).toEqual(['B'])
  })
  it('功能需求：B/C 灰', () => {
    expect([...grayZones({ confirmed: 'function' })].sort()).toEqual(['B', 'C'])
  })
  it('无判型：不置灰', () => {
    expect(grayZones(null).size).toBe(0)
    expect(grayZones({}).size).toBe(0)
  })
  it('置信度判型同样生效', () => {
    expect([...grayZones({ business: 0.1, user: 0.2, function: 0.9 })].sort()).toEqual(['B', 'C'])
  })
})
