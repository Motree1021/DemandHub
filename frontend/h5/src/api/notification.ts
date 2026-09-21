import { get, put } from './request'
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
