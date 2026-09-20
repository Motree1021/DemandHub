import { defineStore } from 'pinia'
import type { UserInfo, LoginResponse } from '@/api/auth'

const TOKEN_KEY = 'demandhub_h5_token'
const REFRESH_KEY = 'demandhub_h5_refresh_token'
const FROM_KEY = 'demandhub_h5_from'

interface UserState {
  token: string
  refreshToken: string
  userInfo: UserInfo | null
  /** 来源标记：chuangjinls 表示从创金零售 App 跳入 */
  from: string
}

export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: localStorage.getItem(TOKEN_KEY) || '',
    refreshToken: localStorage.getItem(REFRESH_KEY) || '',
    userInfo: null,
    from: sessionStorage.getItem(FROM_KEY) || ''
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    name: (state) => state.userInfo?.name || ''
  },
  actions: {
    setLogin(resp: LoginResponse) {
      this.token = resp.accessToken
      this.refreshToken = resp.refreshToken
      this.userInfo = resp.user
      localStorage.setItem(TOKEN_KEY, resp.accessToken)
      localStorage.setItem(REFRESH_KEY, resp.refreshToken)
    },
    setFrom(from: string) {
      this.from = from
      sessionStorage.setItem(FROM_KEY, from)
    }
  }
})
