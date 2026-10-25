/** 需求要素/扩展字段/附件的读取与展示辅助（口径与 H5 提报端 utils/form.ts 一致）。 */
import type { DemandRow, MessageRow, StandardDef, StandardField } from '@/api'

export const fieldPath = (field: StandardField): string => field.path || field.key

/** 标准里的全部字段（要素+公共+可选+子类型），按 path 去重 */
export function allFields(standard: StandardDef): StandardField[] {
  const seen = new Set<string>()
  return [...standard.elements, ...standard.commonFields, ...standard.optionalFields,
    ...Object.values(standard.subtypeFields).flat()].filter(field => {
    const path = fieldPath(field)
    if (seen.has(path)) return false
    seen.add(path)
    return true
  })
}

/** 按字段定义从需求上取值：ext.* → ext 扩展，elements.* → elements[分区][键]，其余取需求顶层字段 */
export function readField(demand: DemandRow, field: StandardField): unknown {
  const path = fieldPath(field)
  if (path.startsWith('ext.')) return demand.ext?.[path.slice(4)]
  if (path.startsWith('elements.')) {
    const [, zone, key] = path.split('.')
    return demand.elements?.[zone]?.[key]
  }
  return (demand as unknown as Record<string, unknown>)[path]
}

/** 值转展示文案：枚举值转选项中文、数组顿号连接、对象 JSON 兜底；空值返回空串便于过滤 */
export function displayValue(value: unknown, field?: StandardField): string {
  if (value == null || value === '') return ''
  const text = Array.isArray(value) ? value.join('、')
    : typeof value === 'object' ? JSON.stringify(value) : String(value)
  return field?.options?.[text] || text
}

/** 五区标题（PRD §4.1 要素分区口径） */
export const ZONE_TITLES: Record<string, string> = {
  A: 'A · 公共要素',
  B: 'B · 业务需求（Why）',
  C: 'C · 用户需求（Who/What）',
  D: 'D · 功能需求（How）',
}

// ---- 判型（ext.typeRecognition）与置灰 ----

/** 判型层级：业务需求 / 用户需求 / 功能需求 */
export type RecognitionLevel = 'business' | 'user' | 'function'

export interface TypeRecognition {
  confirmed?: RecognitionLevel | null
  business?: number
  user?: number
  function?: number
}

export const RECOGNITION_LABELS: Record<RecognitionLevel, string> = {
  business: '业务需求',
  user: '用户需求',
  function: '功能需求',
}

const LEVELS: RecognitionLevel[] = ['business', 'user', 'function']

/** 生效判型：人工确认（confirmed）优先；否则按层级倾斜 + 档位对齐（2026-10-24 拍板 business>user>function）——
 *  business≥0.7（主句级起点）→ business；否则 user≥0.7 → user；否则 → function
 * （function 不参与比较，从句级信号封顶 0.6 天然不过线，与 status.ts demandLevelOf、H5 FormSnapshotCard 同口径）；
 *  无确认且置信度全零返回 null（置灰兜底：视为无判型不置灰） */
export function recognitionLevel(recognition: unknown): RecognitionLevel | null {
  if (!recognition || typeof recognition !== 'object') return null
  const r = recognition as TypeRecognition
  if (r.confirmed && LEVELS.includes(r.confirmed)) return r.confirmed
  const business = Number(r.business) || 0
  const user = Number(r.user) || 0
  const fn = Number(r.function) || 0
  if (!business && !user && !fn) return null
  if (business >= 0.7) return 'business'
  return user >= 0.7 ? 'user' : 'function'
}

/** 判型置灰（2026-10-13 拍板·向下兼容）：业务需求全亮；用户需求 B 灰；功能需求 B/C 灰；无判型不置灰 */
export function grayZones(recognition: unknown): Set<'B' | 'C'> {
  const level = recognitionLevel(recognition)
  if (level === 'user') return new Set(['B'])
  if (level === 'function') return new Set(['B', 'C'])
  return new Set()
}

/** 服务端保留的 ext 键（已有专属展示位：概述/打回原因/预判拆分等），补充信息兜底展示时排除 */
export const RESERVED_EXT_KEYS = ['typeRecognition', 'pendingSplits', 'overview', 'mode', 'returnReason']

/** 操作记录类消息（附件上传/手工改动/打回播报等带结构化工单的），不算提报人原话 */
function isActionMessage(message: MessageRow): boolean {
  if (!message.structuredPayload) return false
  try {
    return !!(JSON.parse(message.structuredPayload) as { kind?: string })?.kind
  } catch { return false }
}

/** 提报人后续补充原话：排除与底稿全等的首条 USER（即底稿本身）与操作记录消息（与 H5 同口径） */
export function userSupplements(demand: DemandRow, messages: MessageRow[]): MessageRow[] {
  const base = (demand.content || '').trim()
  let skipped = false
  return messages.filter(m => {
    if (m.role !== 'USER') return false
    if (isActionMessage(m)) return false
    if (!skipped && base && m.content.trim() === base) { skipped = true; return false }
    return true
  })
}

/** 文件大小人性化显示 */
export function fmtSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}
