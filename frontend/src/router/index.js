import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    children: [
      { path: '', name: 'home', component: () => import('@/views/Home.vue') },
      { path: 'devices', name: 'devices', component: () => import('@/views/Devices.vue') },
      { path: 'history', name: 'history', component: () => import('@/views/History.vue') },
      { path: 'alerts', name: 'alerts', component: () => import('@/views/Alerts.vue') },
      { path: 'prediction', name: 'prediction', component: () => import('@/views/Prediction.vue') },
      {
        path: 'admin/subscription',
        name: 'subscription',
        component: () => import('@/views/admin/Subscription.vue'),
        meta: { admin: true }
      },
      {
        path: 'admin/logs',
        name: 'logs',
        component: () => import('@/views/admin/Logs.vue'),
        meta: { admin: true }
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
})

export default router
