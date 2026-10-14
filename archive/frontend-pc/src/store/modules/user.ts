import { defineStore } from 'pinia'
import type { UserInfo, LoginResponse } from '@/api/auth'
import { me, logout as apiLogout } from '@/api/auth'

const TOKEN_KEY = 'demandhub_token'
const REFRESH_KEY = 'demandhub_refresh_token'

interface UserState {
  token: string
  refreshToken: string
  userInfo: UserInfo | null
}

/**
 * 用户会话 store：token + 用户信息（含角色与生效授权）
 */
export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    refreshToken: localStorage.getItem(REFRESH_KEY) || '',
    userInfo: null
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    name: (state) => state.userInfo?.name || '',
    roles: (state) => state.userInfo?.roles || [],
    isAdmin(): boolean {
      return this.roles.includes('ADMIN')
    }
  },
  actions: {
    /** 登录成功：保存令牌与用户信息 */
    setLogin(resp: LoginResponse) {
      this.token = resp.accessToken
      this.refreshToken = resp.refreshToken
      this.userInfo = resp.user
      localStorage.setItem(TOKEN_KEY, resp.accessToken)
      localStorage.setItem(REFRESH_KEY, resp.refreshToken)
    },
    /** 拉取当前用户信息（页面刷新后恢复会话展示） */
    async fetchMe() {
      this.userInfo = await me()
    },
    /** 登出：通知后端失效会话并清理本地 */
    async logout() {
      if (this.refreshToken) {
        try {
          await apiLogout(this.refreshToken)
        } catch {
          // 后端会话可能已失效，本地照常清理
        }
      }
      this.reset()
    },
    reset() {
      this.token = ''
      this.refreshToken = ''
      this.userInfo = null
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(REFRESH_KEY)
    }
  }
})
