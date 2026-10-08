import type { DemandEntity, DemandForm, Standard, StandardField } from '@/api/demand'
export function newForm(): DemandForm {
  return { title: '', demandTypeCode: 'TECH', content: '', urgency: '', expectDeliveryAt: null, elements: {}, ext: {}, fieldSources: { demandTypeCode: 'default' } }
}
export function formFromDemand(demand: DemandEntity): DemandForm {
  return structuredClone({ title: demand.title, demandTypeCode: demand.demandTypeCode, content: demand.content, urgency: demand.urgency, expectDeliveryAt: demand.expectDeliveryAt, elements: demand.elements || {}, ext: demand.ext || {}, fieldSources: demand.fieldSources || {} })
}
export function fieldPath(field: StandardField): string { return field.path || field.key }
export function allFields(standard: Standard): StandardField[] {
  const seen = new Set<string>()
  return [...standard.elements, ...standard.commonFields, ...standard.optionalFields, ...Object.values(standard.subtypeFields).flat()].filter(field => {
    const path = fieldPath(field)
    if (seen.has(path)) return false
    seen.add(path); return true
  })
}
export function readField(form: DemandForm, field: StandardField): unknown {
  const path = fieldPath(field)
  if (path.startsWith('ext.')) return form.ext[path.slice(4)]
  if (path.startsWith('elements.')) {
    const [, zone, key] = path.split('.')
    return form.elements[zone]?.[key]
  }
  return (form as unknown as Record<string, unknown>)[path]
}
export function writeUserField(form: DemandForm, field: StandardField, value: unknown) {
  const path = fieldPath(field)
  const normalized = field.kind === 'number' ? value === '' ? null : Number(value) : value
  if (path.startsWith('ext.')) form.ext[path.slice(4)] = normalized
  else if (path.startsWith('elements.')) {
    const [, zone, key] = path.split('.')
    ;(form.elements[zone] ||= {})[key] = normalized
  } else (form as unknown as Record<string, unknown>)[path] = normalized
  form.fieldSources[path] = 'user'
}
export function canApplyRevision(currentRevision: number, incomingRevision: number, dirty = false): boolean {
  return !dirty && incomingRevision >= currentRevision
}
