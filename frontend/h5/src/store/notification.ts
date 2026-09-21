import { defineStore } from 'pinia'
import { unreadCount } from '@/api/notification'

const POLL_INTERVAL = 30 * 1000

let timer: ReturnType<typeof setInterval> | null = null

/** 通知未读数（TabBar 角标），登录后 30s 轮询 */
export const useNotificationStore = defineStore('notification', {
  state: () => ({
    unread: 0
  }),
  actions: {
    async refresh() {
      try {
        const resp = await unreadCount()
        this.unread = resp.count
      } catch {
        // 未登录或网络异常时保持原值，不打扰用户
      }
    },
    /** 幂等启动轮询（重复调用不会叠加定时器） */
    startPolling() {
      if (timer) {
        return
      }
      this.refresh()
      timer = setInterval(() => {
        this.refresh()
      }, POLL_INTERVAL)
    },
    stopPolling() {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }
})
