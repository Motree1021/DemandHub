/** 判型识别与置灰规则（utils/demand.ts）：confirmed 优先、层级倾斜 + 档位对齐（判线 0.7）、向下兼容置灰。 */
import { describe, expect, it } from 'vitest'
import type { ElementStatus, StandardDef, StandardField } from '../src/api'
import { grayZones, recognitionLevel, vagueRequiredLabels } from '../src/utils/demand'

describe('recognitionLevel 生效判型', () => {
  it('人工确认优先于置信度', () => {
    expect(recognitionLevel({ confirmed: 'user', business: 0.9, user: 0.1, function: 0 })).toBe('user')
  })
  it('无确认按层级档位判定：business/user ≥0.7（主句级起点）才过线', () => {
    expect(recognitionLevel({ business: 0.2, user: 0.7, function: 0.1 })).toBe('user')
    expect(recognitionLevel({ business: 0.8, user: 0.1, function: 0.1 })).toBe('business')
    // 从句级顶格 0.6 不过 0.7 判线（收益从句封顶天然隔离带）：business 0.6<0.7、user 0.6<0.7 → function
    expect(recognitionLevel({ business: 0.6, user: 0.6, function: 0.8 })).toBe('function')
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

/** 受理兜底（三段防线③）vagueRequiredLabels：必填交互项且质检 VAGUE 的要素标签清单 */
describe('vagueRequiredLabels 笼统必填清单', () => {
  const field = (key: string, label: string, extra: Partial<StandardField> = {}): StandardField =>
    ({ key, label, kind: 'text', ...extra })
  const standardOf = (elements: StandardField[]): StandardDef =>
    ({ type: 'TECH', name: '科技', version: '1', elements, commonFields: [], optionalFields: [], subtypeFields: {} })
  const status = (key: string, s: ElementStatus['status']): ElementStatus => ({ key, status: s, note: '' })

  it('必填交互项且 VAGUE 的要素按标准顺序列出标签', () => {
    const standard = standardOf([
      field('userRole', '目标用户', { required: true }),
      field('userGoal', '用户目标', { required: true }),
      field('acceptanceCriteria', '验收标准', { required: true }),
    ])
    const quality = [status('userRole', 'VAGUE'), status('userGoal', 'OK'), status('acceptanceCriteria', 'VAGUE')]
    expect(vagueRequiredLabels(standard, quality)).toEqual(['目标用户', '验收标准'])
  })
  it('非必填 / 系统快照 / 自动提取 / 底稿 content 一律不列', () => {
    const standard = standardOf([
      field('bizValue', '业务价值'), // 非必填
      field('requester', '提报人', { required: true, system: true }),
      field('title', '标题', { required: true, autoFill: true }),
      field('content', '需求描述', { required: true }),
      field('painPoint', '痛点', { required: true }),
    ])
    const quality = ['bizValue', 'requester', 'title', 'content', 'painPoint'].map(k => status(k, 'VAGUE'))
    expect(vagueRequiredLabels(standard, quality)).toEqual(['痛点'])
  })
  it('OK / MISSING / SKIP 状态不列；无质检记录不列', () => {
    const standard = standardOf([field('userRole', '目标用户', { required: true })])
    expect(vagueRequiredLabels(standard, [status('userRole', 'OK')])).toEqual([])
    expect(vagueRequiredLabels(standard, [status('userRole', 'MISSING')])).toEqual([])
    expect(vagueRequiredLabels(standard, [])).toEqual([])
  })
  it('无标准时返回空清单', () => {
    expect(vagueRequiredLabels(null, [status('userRole', 'VAGUE')])).toEqual([])
    expect(vagueRequiredLabels(undefined, [])).toEqual([])
  })
  it('可选字段/公共字段中的必填 VAGUE 项同样纳入（allFields 全量扫描）', () => {
    const standard = standardOf([field('userRole', '目标用户', { required: true })])
    standard.optionalFields.push(field('expectFinishAt', '期望交付时间', { required: true, kind: 'date' }))
    const quality = [status('userRole', 'OK'), status('expectFinishAt', 'VAGUE')]
    expect(vagueRequiredLabels(standard, quality)).toEqual(['期望交付时间'])
  })
})
