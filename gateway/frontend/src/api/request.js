import axios from 'axios'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import router from '@/router'

const request = axios.create({
  baseURL: '/api',
  timeout: 10000
})

request.interceptors.request.use((config) => {
  const userStore = useUserStore()
  if (userStore.token) {
    config.headers.Authorization = `Bearer ${userStore.token}`
  }
  // pywebview 桌面环境:file:// 协议下 axios 跨域受限,
  // 改用 Python js_api 桥接(http_get/http_post,JWT 由 Python 侧自动携带)
  if (window.pywebview?.api) {
    config.adapter = async (cfg) => {
      const fullPath = (cfg.baseURL || '') + (cfg.url || '')
      const method = (cfg.method || 'get').toLowerCase()
      let result
      if (method === 'get') {
        result = await window.pywebview.api.http_get(fullPath, cfg.params || {})
      } else {
        // POST/PUT/DELETE 均走 http_post(body 即 cfg.data)
        result = await window.pywebview.api.http_post(fullPath, cfg.data || {})
      }
      // result: { status, data }
      if (!result || result.status === 0 || result.status >= 400) {
        const err = new Error(`pywebview request failed: ${result?.status}`)
        err.response = { status: result?.status || 0, data: result?.data }
        err.config = cfg
        throw err
      }
      // 包装成 axios 兼容的 response 格式
      return {
        data: result.data,
        status: result.status,
        statusText: 'OK',
        headers: {},
        config: cfg,
        request: {}
      }
    }
  }
  return config
})

request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const status = err.response?.status
    const msg = err.response?.data?.error || err.message || '请求失败'
    if (status === 401) {
      const userStore = useUserStore()
      userStore.clear()
      if (router.currentRoute.value.name !== 'login') {
        router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
      }
    } else {
      try { useUiStore().pushToast({ type: 'danger', title: '请求失败', message: msg }) } catch (e) {}
    }
    return Promise.reject(err)
  }
)

export default request
