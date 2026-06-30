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
