import { get, post, put } from './request'
import type { PageResult } from './demand'

/* ---------------- 通知中心 ---------------- */

export interface NotificationItem {
  id: number
  demandId: number | null
  receiverId: number
  channel: string
  templateCode: string
  title: string
  content: string
  link: string | null
  isRead: number
  readAt: string | null
  sendStatus: string
  retryCount: number
  createdAt: string
  sentAt: string | null
}

export function pageMyNotifications(q: { current: number; size: number; isRead?: boolean }): Promise<PageResult<NotificationItem>> {
  return get('/notification/mine', q)
}

export function unreadCount(): Promise<{ count: number }> {
  return get('/notification/mine/unread-count')
}

export function markRead(id: number): Promise<void> {
  return put(`/notification/${id}/read`)
}

export function markAllRead(): Promise<{ updated: number }> {
  return put('/notification/mine/read-all')
}

/* ---------------- 通知偏好 ---------------- */

export interface PreferenceItem {
  notifyType: string
  closable: boolean
  enabled: boolean
}

export function listPreferences(): Promise<PreferenceItem[]> {
  return get('/notification/preferences')
}

export function updatePreference(notifyType: string, enabled: boolean): Promise<void> {
  return put('/notification/preferences', { notifyType, enabled })
}

/* ---------------- 通知模板（ADMIN） ---------------- */

export interface TemplateItem {
  id: number
  templateCode: string
  templateName: string
  titleTemplate: string
  contentTemplate: string
  status: string
  remark: string | null
  createdAt: string
  updatedAt: string
}

export function listTemplates(): Promise<TemplateItem[]> {
  return get('/notification/admin/templates')
}

export function createTemplate(data: Partial<TemplateItem>): Promise<TemplateItem> {
  return post('/notification/admin/templates', data)
}

export function updateTemplate(id: number, data: Partial<TemplateItem>): Promise<TemplateItem> {
  return put(`/notification/admin/templates/${id}`, data)
}

export function previewTemplate(templateCode: string, vars: Record<string, unknown>): Promise<{ title: string; content: string }> {
  return post('/notification/admin/templates/preview', { templateCode, vars })
}
