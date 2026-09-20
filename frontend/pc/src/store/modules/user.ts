import { defineStore } from 'pinia'

interface UserState {
  token: string
  userId: string
  name: string
  roles: string[]
}

/**
 * 用户会话 store：阶段 2 接入企微 OAuth 后填充真实数据
 */
export const useUserStore = defineStore('user', {
  state: (): UserState => ({
    token: localStorage.getItem('demandhub_token') || '',
    userId: '',
    name: '',
    roles: []
  }),
  getters: {
    isLoggedIn: (state) => !!state.token
  },
  actions: {
    setToken(token: string) {
      this.token = token
      localStorage.setItem('demandhub_token', token)
    },
    logout() {
      this.token = ''
      this.userId = ''
      this.name = ''
      this.roles = []
      localStorage.removeItem('demandhub_token')
    }
  }
})
