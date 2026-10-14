import { get } from './request'

/** 未读通知数（H5 仅用于「我的需求」tab 角标，不做已读动作） */
export function unreadCount(): Promise<{ count: number }> {
  return get<{ count: number }>('/notification/mine/unread-count', undefined, { silent: true })
}
