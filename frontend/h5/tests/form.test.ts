import { describe, expect, it } from 'vitest'
import { canApplyRevision, newForm, readField, writeUserField } from '@/utils/form'
describe('手填来源与旧结果保护', () => {
  it('默认类型可由Agent改变，用户清空也明确标user', () => {
    const form = newForm(); expect(form.fieldSources.demandTypeCode).toBe('default')
    writeUserField(form, { key: 'businessScenario', path: 'ext.businessScenario', kind: 'text', label: '业务场景' }, '')
    expect(form.ext.businessScenario).toBe(''); expect(form.fieldSources['ext.businessScenario']).toBe('user')
  })
  it('数字字段和日期只保存合法类型的用户值', () => {
    const form = newForm()
    writeUserField(form, { key: 'quantity', path: 'ext.quantity', kind: 'number', label: '数量' }, '12')
    expect(form.ext.quantity).toBe(12)
    writeUserField(form, { key: 'quantity', path: 'ext.quantity', kind: 'number', label: '数量' }, '')
    expect(form.ext.quantity).toBeNull()
    writeUserField(form, { key: 'expectDeliveryAt', kind: 'date', label: '日期' }, '2026-10-01')
    expect(form.expectDeliveryAt).toBe('2026-10-01')
  })
  it('重放旧revision或有未保存手改时不覆盖', () => {
    expect(canApplyRevision(5, 4)).toBe(false); expect(canApplyRevision(5, 6, true)).toBe(false)
    expect(canApplyRevision(5, 6)).toBe(true)
  })
  it('elements三段路径按区分桶读写并标记user来源', () => {
    const form = newForm()
    const field = { key: 'businessGoal', path: 'elements.B.businessGoal', kind: 'text', label: '业务目标' }
    writeUserField(form, field, '把回访覆盖率提升到80%')
    expect(form.elements.B.businessGoal).toBe('把回访覆盖率提升到80%')
    expect(form.fieldSources['elements.B.businessGoal']).toBe('user')
    expect(readField(form, field)).toBe('把回访覆盖率提升到80%')
    expect(form.ext).toEqual({})
    expect(readField(form, { key: 'stakeholders', path: 'elements.B.stakeholders', kind: 'list', label: '干系人' })).toBeUndefined()
  })
})
