import { get, post, put, del } from './request'

/* ---------------- 系统管理 API（均限 ADMIN） ---------------- */

/** 需求类型 */
export interface DemandTypeItem {
  id: number
  typeCode: string
  typeName: string
  parentTypeCode: string | null
  defaultOrgId: number | null
  stateMachineKey: string | null
  slaConfig: string | null
  sort: number
  status: string
}

export function listDemandTypes(): Promise<DemandTypeItem[]> {
  return get('/demand/admin/types')
}

export function createDemandType(data: Partial<DemandTypeItem>): Promise<DemandTypeItem> {
  return post('/demand/admin/types', data)
}

export function updateDemandType(id: number, data: Partial<DemandTypeItem>): Promise<DemandTypeItem> {
  return put(`/demand/admin/types/${id}`, data)
}

/** 状态机配置 */
export interface StateMachineConfigItem {
  id: number
  configKey: string
  configName: string
  configJson: string
  status: string
  remark: string | null
  createdAt: string
  updatedAt: string
}

export function listStateMachines(): Promise<StateMachineConfigItem[]> {
  return get('/demand/admin/state-machines')
}

export function getStateMachineDefaultJson(): Promise<{ configJson: string }> {
  return get('/demand/admin/state-machines/default-json')
}

export function createStateMachine(data: Partial<StateMachineConfigItem>): Promise<StateMachineConfigItem> {
  return post('/demand/admin/state-machines', data)
}

export function updateStateMachine(id: number, data: Partial<StateMachineConfigItem>): Promise<StateMachineConfigItem> {
  return put(`/demand/admin/state-machines/${id}`, data)
}

export function reloadStateMachines(): Promise<void> {
  return post('/demand/admin/state-machines/reload')
}

/** 通用字典 */
export interface SysDictItem {
  id: number
  dictType: string
  itemCode: string
  itemName: string
  sort: number
  status: string
}

export function listSysDicts(dictType?: string): Promise<SysDictItem[]> {
  return get('/demand/admin/dicts', dictType ? { dictType } : undefined)
}

export function listSysDictTypes(): Promise<string[]> {
  return get('/demand/admin/dicts/types')
}

export function createSysDict(data: Partial<SysDictItem>): Promise<SysDictItem> {
  return post('/demand/admin/dicts', data)
}

export function updateSysDict(id: number, data: Partial<SysDictItem>): Promise<SysDictItem> {
  return put(`/demand/admin/dicts/${id}`, data)
}

/** SLA 配置 */
export interface SlaConfigItem {
  id: number
  demandTypeCode: string
  status: string
  warnMinutes: number
  maxMinutes: number
  enabled: number
  remark: string | null
  createdAt: string
  updatedAt: string
}

export function listSlaConfigs(demandTypeCode?: string): Promise<SlaConfigItem[]> {
  return get('/demand/admin/sla-configs', demandTypeCode ? { demandTypeCode } : undefined)
}

export function createSlaConfig(data: Partial<SlaConfigItem>): Promise<SlaConfigItem> {
  return post('/demand/admin/sla-configs', data)
}

export function updateSlaConfig(id: number, data: Partial<SlaConfigItem>): Promise<SlaConfigItem> {
  return put(`/demand/admin/sla-configs/${id}`, data)
}

export function deleteSlaConfig(id: number): Promise<void> {
  return del(`/demand/admin/sla-configs/${id}`)
}
