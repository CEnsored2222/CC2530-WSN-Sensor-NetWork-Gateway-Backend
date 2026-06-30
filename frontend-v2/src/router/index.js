import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { connectSocket, disconnectSocket, getSocket } from '@/ws/socket'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true, transition: 'route' }
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    children: [
      { path: '', name: 'home', component: () => import('@/views/Home.vue'), meta: { transition: 'route' } },
      { path: 'devices', name: 'devices', component: () => import('@/views/Devices.vue'), meta: { transition: 'route' } },
      { path: 'history', name: 'history', component: () => import('@/views/History.vue'), meta: { transition: 'route' } },
      { path: 'alerts', name: 'alerts', component: () => import('@/views/Alerts.vue'), meta: { transition: 'route' } },
      { path: 'prediction', name: 'prediction', component: () => import('@/views/Prediction.vue'), meta: { transition: 'route' } },
      { path: 'vision', name: 'vision', component: () => import('@/views/Vision.vue'), meta: { transition: 'route' } },
      {
        path: 'admin/subscription',
        name: 'subscription',
        component: () => import('@/views/admin/Subscription.vue'),
        meta: { admin: true, transition: 'route' }
      },
      {
        path: 'admin/logs',
        name: 'logs',
        component: () => import('@/views/admin/Logs.vue'),
        meta: { admin: true, transition: 'route' }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', redirect: '/' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

router.beforeEach((to) => {
  const userStore = useUserStore()
  if (!to.meta.public && !userStore.token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.admin && userStore.role !== 'admin') {
    return { name: 'home' }
  }
  if (to.name === 'login' && userStore.token) {
    return { name: 'home' }
  }

  // WS 连接生命周期:token 存在且 WS 未连接时建立;离开登录页/登出时断开由各处处理
  if (userStore.token && to.name !== 'login') {
    const s = getSocket()
    if (!s.connected) connectSocket()
  }
  if (to.name === 'login') {
    disconnectSocket()
  }
})

export default router
