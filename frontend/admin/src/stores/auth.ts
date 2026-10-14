import { defineStore } from 'pinia'
import { authApi } from '@/api'
import type { LoginUser } from '@/api'
import { clearTokens, getAccessToken, getRefreshToken, saveTokens } from '@/api/request'

interface AuthState {
  user: LoginUser | null
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({ user: null }),
  getters: {
    isLoggedIn: () => !!getAccessToken(),
    mustChangePwd: state => state.user?.mustChangePwd ?? false,
    role: state => state.user?.role ?? null,
  },
  actions: {
    async login(loginAccount: string, password: string) {
      const data = await authApi.login(loginAccount, password)
      saveTokens(data.accessToken, data.refreshToken)
      this.user = { ...data.user, mustChangePwd: data.mustChangePwd }
    },
    async fetchMe() {
      this.user = await authApi.me()
    },
    async changePassword(oldPassword: string, newPassword: string) {
      await authApi.changePassword(oldPassword, newPassword)
      if (this.user) this.user.mustChangePwd = false
    },
    async logout() {
      const refreshToken = getRefreshToken()
      if (refreshToken) await authApi.logout(refreshToken).catch(() => undefined)
      clearTokens()
      this.user = null
    },
  },
})
