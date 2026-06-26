<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { connectSocket, disconnectSocket } from '@/ws/socket'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

const navItems = computed(() => {
  const base = [
    { idx: '01', label: '实时监控', name: 'home' },
    { idx: '02', label: '设备管理', name: 'devices' },
    { idx: '03', label: '历史曲线', name: 'history' },
    { idx: '04', label: '预警中心', name: 'alerts' },
    { idx: '05', label: '智能预测', name: 'prediction' }
  ]
  if (userStore.isAdmin) {
    base.push({ idx: '06', label: '订阅管理', name: 'subscription' })
    base.push({ idx: '07', label: '日志管理', name: 'logs' })
  }
  return base
})

const pageTitle = computed(() => {
  const found = navItems.value.find((i) => i.name === route.name)
  return found ? found.label : 'Atmos'
})

const wsConnected = ref(false)

onMounted(() => {
  const s = connectSocket()
  wsConnected.value = s.connected
  s.on('connect', () => (wsConnected.value = true))
  s.on('disconnect', () => (wsConnected.value = false))
})

onUnmounted(() => {
  disconnectSocket()
})

async function logout() {
  await ElMessageBox.confirm('确定退出登录吗?', '退出', {
    confirmButtonText: '退出',
    cancelButtonText: '取消',
    type: 'warning'
  }).catch(() => 'cancel')
    .then((v) => {
      if (v === 'cancel') return
      userStore.clear()
      disconnectSocket()
      router.push({ name: 'login' })
    })
}
</script>

<template>
  <div class="shell">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark"></span>
        <div class="brand-text">
          <div class="brand-name display">Atmos</div>
          <div class="brand-sub label-eyebrow">Home Telemetry</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          :class="{ active: route.name === item.name }"
        >
          <span class="nav-idx mono">{{ item.idx }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-bar"></span>
        </RouterLink>
      </nav>

      <div class="side-foot">
        <div class="user-block">
          <div class="avatar">{{ userStore.username.slice(0, 1).toUpperCase() }}</div>
          <div class="user-meta">
            <div class="user-name">{{ userStore.username }}</div>
            <div class="user-role label-eyebrow">{{ userStore.role }}</div>
          </div>
        </div>
        <button class="logout" @click="logout">退出</button>
      </div>
    </aside>

    <!-- 主区 -->
    <main class="main">
      <header class="topbar">
        <div class="page-title display">{{ pageTitle }}</div>
        <div class="top-right">
          <button class="theme-toggle" :title="themeStore.theme === 'dark' ? '切换到亮色' : '切换到暗色'" @click="themeStore.toggle()">
            <span class="tt-track">
              <span class="tt-thumb" :class="{ right: themeStore.theme === 'light' }">
                <span class="tt-ico">{{ themeStore.theme === 'dark' ? '☾' : '☀' }}</span>
              </span>
            </span>
          </button>
          <span class="ws-state" :class="{ on: wsConnected }">
            <span class="ws-dot"></span>
            <span class="ws-text mono">{{ wsConnected ? 'LIVE' : '连接中' }}</span>
          </span>
        </div>
      </header>
      <div class="content">
        <RouterView v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </RouterView>
      </div>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 248px 1fr;
  height: 100vh;
  overflow: hidden;
}

/* —— 侧边栏 —— */
.sidebar {
  background: var(--paper-deep);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 30px 22px;
  position: relative;
}
.sidebar::after {
  content: '';
  position: absolute;
  right: 0;
  top: 30%;
  bottom: 30%;
  width: 1px;
  background: linear-gradient(transparent, var(--line-strong), transparent);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 6px 32px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 28px;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, var(--sage) 0%, var(--sage-deep) 70%);
  box-shadow: 0 0 0 4px var(--sage-tint);
  flex-shrink: 0;
}
.brand-name {
  font-size: 26px;
  line-height: 1;
  font-weight: 500;
}
.brand-sub {
  margin-top: 4px;
  color: var(--ink-4);
  font-size: 9px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 13px 14px;
  border-radius: var(--radius);
  color: var(--ink-3);
  transition: all 0.25s var(--ease);
}
.nav-item:hover {
  color: var(--ink);
  background: var(--sage-tint);
}
.nav-idx {
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0.06em;
  width: 18px;
  transition: color 0.25s var(--ease);
}
.nav-label {
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.01em;
}
.nav-bar {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 3px;
  height: 20px;
  background: var(--sage);
  border-radius: 0 3px 3px 0;
  transition: transform 0.3s var(--ease);
}
.nav-item.active {
  color: var(--ink);
  background: var(--surface);
}
.nav-item.active .nav-idx {
  color: var(--sage);
}
.nav-item.active .nav-bar {
  transform: translateY(-50%) scaleY(1);
}

.side-foot {
  border-top: 1px solid var(--line);
  padding-top: 18px;
}
.user-block {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--sage);
  color: #fff;
  display: grid;
  place-items: center;
  font-family: var(--font-display);
  font-weight: 500;
  font-size: 15px;
  flex-shrink: 0;
}
.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink);
}
.user-role {
  color: var(--ink-4);
  font-size: 9px;
  text-transform: uppercase;
  margin-top: 2px;
}
.logout {
  width: 100%;
  border: 1px solid var(--line-strong);
  background: transparent;
  border-radius: var(--radius);
  padding: 8px;
  color: var(--ink-3);
  font-size: 12px;
  letter-spacing: 0.04em;
  transition: all 0.2s var(--ease);
}
.logout:hover {
  border-color: var(--terra);
  color: var(--terra);
}

/* —— 主区 —— */
.main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.topbar {
  height: 72px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  background: color-mix(in srgb, var(--paper) 78%, transparent);
  backdrop-filter: blur(10px) saturate(1.2);
}
.top-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

/* —— 主题切换 —— */
.theme-toggle {
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}
.tt-track {
  width: 52px;
  height: 26px;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  display: inline-flex;
  align-items: center;
  padding: 2px;
  position: relative;
  transition: all 0.3s var(--ease);
}
.tt-track:hover { border-color: var(--sage); }
.tt-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--sage);
  color: #06141a;
  display: grid;
  place-items: center;
  font-size: 11px;
  transition: transform 0.32s var(--ease);
  box-shadow: 0 0 12px var(--sage-soft);
}
.tt-thumb.right { transform: translateX(26px); }
.tt-ico { font-family: var(--font-mono); line-height: 1; }
.page-title {
  font-size: 24px;
  font-weight: 400;
  letter-spacing: -0.01em;
}
.ws-state {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface);
}
.ws-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 0 3px var(--amber-soft);
}
.ws-state.on .ws-dot {
  background: var(--sage);
  box-shadow: 0 0 0 3px var(--sage-soft);
  animation: breathe 2.4s ease-in-out infinite;
}
.ws-text {
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--ink-3);
}
.ws-state.on .ws-text {
  color: var(--sage-deep);
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 34px 40px 48px;
}
</style>
