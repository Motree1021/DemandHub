import { get, post, put, downloadFile } from './request'
export type FieldSources = Record<string, 'default' | 'agent' | 'user'>
export interface ElementStatus { key: string; label?: string; status: 'OK' | 'VAGUE' | 'MISSING' | 'SKIP'; note: string; attempts: number }
export interface StandardField {
  key: string; label: string; path?: string | null; kind: 'text' | 'enum' | 'number' | 'date' | 'list'
  zone?: 'A' | 'B' | 'C' | 'D' | null; code?: string; system?: boolean
  options?: Record<string, string>; placeholder?: string; required?: boolean; default?: unknown
  okWhen?: string; example?: string; rule?: { minLen?: number; maxLen?: number }
}
export interface Standard {
  type: string; name: string; version: string; contentHash: string; elements: StandardField[]
  optionalFields: StandardField[]; commonFields: StandardField[]; subtypeFields: Record<string, StandardField[]>
  followUpOrder: string[]
}
export interface StandardSummary { code: string; name: string; description?: string }
export type ZoneElements = Record<string, Record<string, unknown>>
export interface DemandForm {
  title: string | null; demandTypeCode: string | null; content: string | null; urgency: string | null
  expectDeliveryAt: string | null; elements: ZoneElements; ext: Record<string, unknown>; fieldSources: FieldSources
}
export interface ChangeLog { id: number; fieldKey: string; oldValue: unknown; newValue: unknown; source: 'default' | 'agent' | 'user'; changedBy: number | null; createdAt: string }
export interface TypeRecognition { business?: number; user?: number; function?: number; confirmed?: string | null; evidence?: Record<string, string> }
export interface DemandEntity extends DemandForm {
  id: number; demandNo: string | null; subtypeCode: string | null; revision: number; status: 'DRAFT' | 'SUBMITTED' | 'CLOSED'
  submitterId: number; submitterName: string | null; submitterDept: string | null; channel: string; sessionId: number | null
  submittedAt: string | null; closedAt: string | null; closeReason: string | null; createdAt: string; updatedAt: string; quality: ElementStatus[]
  changeLogs: ChangeLog[]
}
export interface AgentMessage { id: number; sessionId: number; role: 'USER' | 'ASSISTANT' | 'SYSTEM'; content: string; structuredPayload: string | null; requestId?: string; createdAt: string }
export interface DemandDetail { demand: DemandEntity; quality: ElementStatus[]; standard: Standard | null; messages: AgentMessage[] }
export interface PageResult<T> { records: T[]; total: number; size: number; current: number; pages: number }
export interface DemandQuery { page: number; size: number; status?: string }
export interface AdminQuery extends DemandQuery { type?: string; from?: string; to?: string }
export const getStandards = (): Promise<StandardSummary[]> => get('/standards')
export const getStandard = (type: string): Promise<Standard> => get(`/standards/${type}`)
export const createDraft = (data: DemandForm & { clientRequestId: string }): Promise<DemandEntity> => post('/demand', data)
export const updateDraft = (id: number, data: DemandForm & { expectedRevision: number; notifyChanges?: boolean }): Promise<DemandEntity> => put(`/demand/${id}`, data)
export const submitDemand = (id: number, expectedRevision: number): Promise<DemandEntity> => post(`/demand/${id}/submit`, { expectedRevision })
export const closeDemand = (id: number, reason: string): Promise<DemandEntity> => post(`/demand/${id}/close`, { reason })
export function nonEmptyQuery<T extends object>(query: T): Partial<T> {
  return Object.fromEntries(Object.entries(query).filter(([, value]) => value !== '' && value !== null && value !== undefined)) as Partial<T>
}
export const myDemands = (query: DemandQuery): Promise<PageResult<DemandEntity>> => get('/demand/my', nonEmptyQuery(query))
export const adminDemands = (query: AdminQuery): Promise<PageResult<DemandEntity>> => get('/admin/demand/list', nonEmptyQuery(query))
export const getDemand = (id: number): Promise<DemandDetail> => get(`/demand/${id}`)
export const downloadMarkdown = (id: number, name: string): Promise<void> => downloadFile(`/demand/${id}/export.md`, `${name}.md`)
export const downloadXlsx = (query: Omit<AdminQuery, 'page' | 'size'>): Promise<void> => downloadFile('/admin/demand/export.xlsx', 'demandhub.xlsx', nonEmptyQuery(query) as Record<string, string>)
