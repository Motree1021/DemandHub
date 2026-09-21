import { defineStore } from 'pinia'
import { unreadCount } from '@/api/notification'

const POLL_INTERVAL = 30_000

/**
 * 通知未读数 store：顶栏铃铛角标数据源，30s 轮询 + 页面操作后主动刷新。
 */
export const useNotificationStore = defineStore('notification', {
  state: () => ({
    unread: 0,
    timer: 0 as unknown as ReturnType<typeof setInterval> | null
  }),
  actions: {
    async refresh() {
      try {
        const res = await unreadCount()
        this.unread = res.count
      } catch {
        // 未登录或网络异常时保持原值
      }
    },
    startPolling() {
      this.stopPolling()
      this.refresh()
      this.timer = setInterval(() => this.refresh(), POLL_INTERVAL)
    },
    stopPolling() {
      if (this.timer) {
        clearInterval(this.timer)
        this.timer = null
      }
    }
  }
})
