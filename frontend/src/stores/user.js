import { defineStore } from 'pinia'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('atmos_token') || '',
    user: JSON.parse(localStorage.getItem('atmos_user') || 'null')
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
    role: (s) => s.user?.role || '',
    isAdmin: (s) => s.user?.role === 'admin',
    username: (s) => s.user?.username || ''
  },
  actions: {
    setAuth(token, user) {
      this.token = token
      this.user = user
      localStorage.setItem('atmos_token', token)
      localStorage.setItem('atmos_user', JSON.stringify(user))
    },
    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem('atmos_token')
      localStorage.removeItem('atmos_user')
    }
  }
})
