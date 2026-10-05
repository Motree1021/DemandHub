import { defineStore } from 'pinia'
import type { UserInfo, LoginResponse } from '@/api/auth'
import { TOKEN_KEY } from '@/api/request'
const FROM_KEY = 'demandhub_h5_from'
export const useUserStore = defineStore('user', {
  state: () => ({ token: localStorage.getItem(TOKEN_KEY) || '', userInfo: null as UserInfo | null, from: sessionStorage.getItem(FROM_KEY) || '' }),
  getters: { isLoggedIn: state => !!state.token, name: state => state.userInfo?.name || '' },
  actions: {
    setLogin(resp: LoginResponse) { this.token = resp.accessToken; this.userInfo = resp.user; localStorage.setItem(TOKEN_KEY, resp.accessToken) },
    setUserInfo(user: UserInfo) { this.userInfo = user },
    setFrom(from: string) { this.from = from; sessionStorage.setItem(FROM_KEY, from) },
    clear() { this.token = ''; this.userInfo = null; localStorage.removeItem(TOKEN_KEY); localStorage.removeItem('demandhub_h5_refresh_token') }
  }
})
