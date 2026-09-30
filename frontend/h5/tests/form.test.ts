import { describe, expect, it } from 'vitest'
import { canApplyRevision, newForm, writeUserField } from '@/utils/form'
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
})
