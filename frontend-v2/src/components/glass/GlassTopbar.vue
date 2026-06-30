<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { getSocket, disconnectSocket } from '@/ws/socket'
import Icon from '@/components/icons/Icon.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

const wsStatus = ref('disconnected')
const userMenuOpen = ref(false)

const pageTitle = computed(() => ({
  home: '总览', devices: '设备', history: '历史',
  alerts: '告警', prediction: '预测',
  subscription: '订阅', logs: '日志', login: 'Atmos'
}[route.name] || 'Atmos'))

const wsConfig = computed(() => ({
  connected: { dot: 'status-dot--connected', text: '已连接', color: 'var(--mint)' },
  connecting: { dot: 'status-dot--connecting', text: '连接中', color: 'var(--amber-soft)' },
  disconnected: { dot: 'status-dot--disconnected', text: '已断开', color: 'var(--color-danger)' }
}[wsStatus.value]))

function updateWs() {
  const s = getSocket()
  wsStatus.value = s.connected ? 'connected' : 'connecting'
}
function logout() {
  disconnectSocket()
  userStore.clear()
  router.push('/login')
}
let socket
function onDisconnect() { wsStatus.value = 'disconnected' }
function onConnectError() { wsStatus.value = 'connecting' }
onMounted(() => {
  socket = getSocket()
  socket.on('connect', updateWs)
  socket.on('disconnect', onDisconnect)
  socket.on('connect_error', onConnectError)
  updateWs()
})
onBeforeUnmount(() => {
  if (socket) {
    socket.off('connect', updateWs)
    socket.off('disconnect', onDisconnect)
    socket.off('connect_error', onConnectError)
  }
})
</script>

<template>
  <header class="topbar">
    <div class="topbar-pill glass-liquid">
      <RouterLink to="/" class="topbar-brand" data-cursor-target>
        <span class="topbar-mark">A</span>
        <span class="topbar-name font-display">{{ pageTitle }}</span>
      </RouterLink>

      <span class="topbar-sep" />

      <div class="topbar-ws">
        <span :class="['status-dot', wsConfig.dot]" />
        <span class="topbar-ws-text" :style="{ color: wsConfig.color }">{{ wsConfig.text }}</span>
      </div>

      <span class="topbar-sep" />

      <button
        class="topbar-icon-btn"
        data-cursor-target
        :aria-label="themeStore.theme === 'dark' ? '切换到亮色' : '切换到暗色'"
        @click="themeStore.toggle()"
      >
        <Icon :name="themeStore.theme === 'dark' ? 'sun' : 'moon'" :size="15" />
      </button>

      <div class="topbar-user">
        <button class="topbar-avatar" data-cursor-target @click="userMenuOpen = !userMenuOpen">
          {{ (userStore.username || 'U').charAt(0).toUpperCase() }}
        </button>
        <Transition
          enter-active-class="transition-all duration-200 ease-out"
          enter-from-class="opacity-0 -translate-y-2"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition-all duration-150 ease-in"
          leave-from-class="opacity-100"
          leave-to-class="opacity-0"
        >
          <div v-if="userMenuOpen" class="topbar-menu glass-liquid" @click="userMenuOpen = false">
            <div class="topbar-menu-head">
              <p class="topbar-menu-name">{{ userStore.username }}</p>
              <p class="topbar-menu-role">{{ userStore.role === 'admin' ? '管理员' : '用户' }}</p>
            </div>
            <button class="topbar-menu-item" data-cursor-target @click="logout">
              <Icon name="logout" :size="14" /> 退出登录
            </button>
          </div>
        </Transition>
      </div>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  position: fixed;
  top: 18px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 50;
}
.topbar-pill {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
}
.topbar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
}
.topbar-mark {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #84cc16, #14b8a6);
  color: #fff;
  font-weight: 700;
  font-size: 12px;
  box-shadow: 0 0 12px rgba(52, 211, 153, 0.35);
}
.topbar-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.topbar-sep {
  width: 1px;
  height: 14px;
  background: var(--glass-border);
}
.topbar-ws {
  display: flex;
  align-items: center;
  gap: 6px;
}
.topbar-ws-text {
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  letter-spacing: 0.04em;
}
@media (max-width: 640px) {
  .topbar-ws-text { display: none; }
}
.topbar-icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  transition: transform 0.2s ease, color 0.2s ease;
}
.topbar-icon-btn:hover {
  transform: scale(1.1);
  color: var(--mint);
}
.topbar-avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background: linear-gradient(135deg, #84cc16, #14b8a6);
  color: #fff;
  font-weight: 700;
  font-size: 11px;
  border: none;
  transition: transform 0.2s ease;
}
.topbar-avatar:hover { transform: scale(1.08); }
.topbar-user { position: relative; }
.topbar-menu {
  position: absolute;
  right: 0;
  top: 38px;
  width: 180px;
  padding: 6px;
  border-radius: 14px;
}
.topbar-menu-head {
  padding: 10px 12px;
  border-bottom: 1px solid var(--glass-border);
  margin-bottom: 4px;
}
.topbar-menu-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.topbar-menu-role {
  font-size: 11px;
  margin-top: 2px;
  color: var(--text-tertiary);
}
.topbar-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  font-size: 13px;
  cursor: pointer;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: 10px;
  transition: background 0.2s ease, color 0.2s ease;
}
.topbar-menu-item:hover {
  background: rgba(132, 204, 22, 0.10);
  color: var(--text-primary);
}
</style>
