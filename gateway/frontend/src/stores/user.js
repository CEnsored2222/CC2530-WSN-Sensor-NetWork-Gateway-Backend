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
      // pywebview 桌面环境:将 JWT 持久化到 Python 侧(http_get/http_post 自动携带)
      try {
        if (window.pywebview?.api?.set_jwt) {
          window.pywebview.api.set_jwt(token)
        }
      } catch (e) {}
    },
    clear() {
      this.token = ''
      this.user = null
      localStorage.removeItem('atmos_token')
      localStorage.removeItem('atmos_user')
      // pywebview 桌面环境:清除 Python 侧持久化的 JWT
      try {
        if (window.pywebview?.api?.logout) {
          window.pywebview.api.logout()
        }
      } catch (e) {}
    }
  }
})
