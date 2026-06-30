<script setup>
import { computed, onMounted, onUnmounted, ref, markRaw } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  Monitor,
  Cpu,
  TrendCharts,
  Bell,
  DataAnalysis,
  Connection,
  Document,
  Camera,
  Fold,
  Close,
  Operation,
  Switch,
  SwitchButton as IconLogout
} from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { connectSocket, disconnectSocket } from '@/ws/socket'
import AlertNotify from '@/components/AlertNotify.vue'

// 拆分面板需要直接渲染各视图组件(URL 不变,仅作"预览"面板)
import HomeView from '@/views/Home.vue'
import DevicesView from '@/views/Devices.vue'
import HistoryView from '@/views/History.vue'
import AlertsView from '@/views/Alerts.vue'
import PredictionView from '@/views/Prediction.vue'
import VisionView from '@/views/Vision.vue'
import SubscriptionView from '@/views/admin/Subscription.vue'
import LogsView from '@/views/admin/Logs.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const themeStore = useThemeStore()

// —— 导航项 ——
// 每项绑定一个 Element Plus 图标组件(markRaw 避免被 Vue 转成响应式代理,性能更好)
const ICON_MAP = {
  home:         markRaw(Monitor),
  devices:      markRaw(Cpu),
  history:      markRaw(TrendCharts),
  alerts:       markRaw(Bell),
  prediction:   markRaw(DataAnalysis),
  vision:       markRaw(Camera),
  subscription: markRaw(Connection),
  logs:         markRaw(Document)
}

const VIEW_MAP = {
  home:         markRaw(HomeView),
  devices:      markRaw(DevicesView),
  history:      markRaw(HistoryView),
  alerts:       markRaw(AlertsView),
  prediction:   markRaw(PredictionView),
  vision:       markRaw(VisionView),
  subscription: markRaw(SubscriptionView),
  logs:         markRaw(LogsView)
}

const navItems = computed(() => {
  const base = [
    { idx: '01', label: '实时监控', name: 'home' },
    { idx: '02', label: '设备管理', name: 'devices' },
    { idx: '03', label: '历史曲线', name: 'history' },
    { idx: '04', label: '预警中心', name: 'alerts' },
    { idx: '05', label: '智能预测', name: 'prediction' },
    { idx: '06', label: '视觉检测', name: 'vision' }
  ]
  if (userStore.isAdmin) {
    base.push({ idx: '07', label: '订阅管理', name: 'subscription' })
    base.push({ idx: '08', label: '日志管理', name: 'logs' })
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

/* ============================================================
   侧边栏宽度缩放(会话内,不持久化)
   ============================================================ */
const sidebarWidth = ref(248)
const SIDEBAR_MIN = 212
const SIDEBAR_MAX = 380
const resizingSidebar = ref(false)

function onSidebarResizeStart(e) {
  e.preventDefault()
  resizingSidebar.value = true
  const startX = e.clientX
  const startW = sidebarWidth.value
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  function onMove(ev) {
    const dx = ev.clientX - startX
    const w = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, startW + dx))
    sidebarWidth.value = w
  }
  function onUp() {
    resizingSidebar.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

/* ============================================================
   拖拽侧边栏选项 → 主区拆分双面板
   - 拖拽时主区显示醒目的 drop 提示
   - 落下后:主区左=当前路由,右=被拖入的路由(预览面板,URL 不变)
   - 拆分比例可拖动中间分隔条调整
   ============================================================ */
const dragRouteName = ref(null)        // 当前正在被拖拽的 nav name
const dragOverMain = ref(false)        // 主区是否处于 dragover 态
const splitRoute = ref(null)           // 拆分面板要渲染的 route name
const splitOpen = ref(false)
const splitRatio = ref(0.5)            // 右侧面板占比 0.28 ~ 0.72
const resizingSplit = ref(false)
const mainRef = ref(null)

const splitComponent = computed(() => (splitRoute.value ? VIEW_MAP[splitRoute.value] : null))
const splitTitle = computed(() => {
  const found = navItems.value.find((i) => i.name === splitRoute.value)
  return found ? found.label : ''
})

function onNavDragStart(e, name) {
  dragRouteName.value = name
  e.dataTransfer.effectAllowed = 'copy'
  e.dataTransfer.setData('text/plain', name)
  // 透明拖拽影像可由浏览器默认生成,这里不显式设置
}
function onNavDragEnd() {
  dragRouteName.value = null
  dragOverMain.value = false
}

function onMainDragOver(e) {
  // 仅当拖入的是非当前路由、且与当前主面板不同时才允许 drop
  if (!dragRouteName.value) return
  if (dragRouteName.value === route.name) {
    e.dataTransfer.dropEffect = 'none'
    return
  }
  e.preventDefault()
  e.dataTransfer.dropEffect = 'copy'
  dragOverMain.value = true
}
function onMainDragLeave(e) {
  // 只有真正离开 main 容器才清掉高亮(避免子元素切换抖动)
  if (!mainRef.value) return
  const related = e.relatedTarget
  if (!related || !mainRef.value.contains(related)) {
    dragOverMain.value = false
  }
}
function onMainDrop(e) {
  e.preventDefault()
  dragOverMain.value = false
  const name = dragRouteName.value
  dragRouteName.value = null
  if (!name || name === route.name) return
  // 不允许拆分自身
  if (!VIEW_MAP[name]) return
  splitRoute.value = name
  splitOpen.value = true
  if (splitRatio.value == null) splitRatio.value = 0.5
}

function closeSplit() {
  splitOpen.value = false
  splitRoute.value = null
}

// 拖动分隔条调整左右面板比例
function onSplitDividerDown(e) {
  e.preventDefault()
  resizingSplit.value = true
  const startX = e.clientX
  const startRatio = splitRatio.value
  const totalW = mainRef.value ? mainRef.value.clientWidth : 1
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  function onMove(ev) {
    const dx = ev.clientX - startX
    let r = startRatio + dx / totalW
    r = Math.min(0.72, Math.max(0.28, r))
    splitRatio.value = r
  }
  function onUp() {
    resizingSplit.value = false
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
</script>

<template>
  <div
    class="shell"
    :class="{ 'is-resizing': resizingSidebar || resizingSplit }"
    :style="{ gridTemplateColumns: sidebarWidth + 'px 1fr' }"
  >
    <!-- 侧边栏 -->
    <aside class="sidebar" :style="{ width: sidebarWidth + 'px' }">
      <div class="brand">
        <span class="brand-mark">
          <span class="brand-mark-core"></span>
          <span class="brand-mark-ring"></span>
        </span>
        <div class="brand-text">
          <div class="brand-name display">Atmos</div>
          <div class="brand-sub label-eyebrow">Home Telemetry</div>
        </div>
      </div>

      <div class="nav-section-label label-eyebrow">Navigation</div>
      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="nav-item"
          :class="{
            active: route.name === item.name,
            'is-primary-split': splitOpen && route.name === item.name,
            'is-split-target': splitRoute === item.name
          }"
          draggable="true"
          @dragstart="onNavDragStart($event, item.name)"
          @dragend="onNavDragEnd"
          :title="splitOpen && route.name === item.name ? '主面板' : (splitRoute === item.name ? '拆分面板中' : '拖到主区可拆分视图')"
        >
          <span class="nav-icon">
            <el-icon :size="16"><component :is="ICON_MAP[item.name]" /></el-icon>
          </span>
          <span class="nav-idx mono">{{ item.idx }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-bar"></span>
          <span class="nav-grip" aria-hidden="true">
            <el-icon :size="11"><Operation /></el-icon>
          </span>
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
        <button class="logout" @click="logout">
          <el-icon :size="14"><IconLogout /></el-icon>
          <span>退出登录</span>
        </button>
      </div>

      <!-- 右边缘缩放手柄 -->
      <div
        class="sidebar-resizer"
        @mousedown="onSidebarResizeStart"
        @dblclick="sidebarWidth = 248"
        title="拖动缩放侧边栏 · 双击复位"
      >
        <span class="resizer-grip"></span>
      </div>
    </aside>

    <!-- 主区 -->
    <main
      ref="mainRef"
      class="main"
      :class="{ 'drag-over': dragOverMain, 'split-on': splitOpen }"
      @dragover="onMainDragOver"
      @dragleave="onMainDragLeave"
      @drop="onMainDrop"
    >
      <header class="topbar">
        <div class="page-title-wrap">
          <span class="page-glyph">
            <el-icon :size="20"><component :is="ICON_MAP[route.name] || Monitor" /></el-icon>
          </span>
          <div>
            <div class="page-eyebrow label-eyebrow">{{ wsConnected ? 'Live Workspace' : 'Workspace' }}</div>
            <div class="page-title display">{{ pageTitle }}</div>
          </div>
        </div>
        <div class="top-right">
          <button
            v-if="splitOpen"
            class="ghost-btn"
            @click="closeSplit"
            title="关闭拆分面板"
          >
            <el-icon :size="14"><Fold /></el-icon>
            <span>收起拆分</span>
          </button>
          <button
            class="theme-toggle"
            :title="themeStore.theme === 'dark' ? '切换到亮色' : '切换到暗色'"
            @click="themeStore.toggle()"
          >
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

      <div class="content-wrap">
        <!-- 主(左)面板 -->
        <section class="pane pane-primary">
          <div class="pane-tag label-eyebrow">Primary</div>
          <div class="content">
            <RouterView v-slot="{ Component }">
              <transition name="page" mode="out-in">
                <component :is="Component" />
              </transition>
            </RouterView>
          </div>
        </section>

        <!-- 分隔条 -->
        <div
          v-if="splitOpen"
          class="split-divider"
          @mousedown="onSplitDividerDown"
          title="拖动调整面板比例"
        >
          <span class="split-divider-grip"></span>
        </div>

        <!-- 拆分(右)面板 -->
        <section
          v-if="splitOpen && splitComponent"
          class="pane pane-split"
          :style="{ flexBasis: (splitRatio * 100) + '%' }"
        >
          <div class="pane-head">
            <div class="pane-head-left">
              <span class="pane-tag split label-eyebrow">Split</span>
              <span class="pane-split-title display">
                <el-icon :size="14" class="pane-split-ico"><component :is="ICON_MAP[splitRoute]" /></el-icon>
                {{ splitTitle }}
              </span>
            </div>
            <button class="pane-close" @click="closeSplit" title="关闭拆分">
              <el-icon :size="14"><Close /></el-icon>
            </button>
          </div>
          <div class="pane-split-body">
            <component :is="splitComponent" :key="splitRoute" />
          </div>
        </section>

        <!-- 拖拽提示遮罩 -->
        <div v-if="dragOverMain" class="drop-hint" aria-hidden="true">
          <div class="drop-hint-inner">
            <div class="drop-hint-glyph">
              <el-icon :size="34"><Switch /></el-icon>
            </div>
            <div class="drop-hint-title display">释放以拆分视图</div>
            <div class="drop-hint-sub label-eyebrow">将在右侧并排打开 · 当前页保留</div>
          </div>
        </div>
      </div>
    </main>

    <!-- 全局通报弹窗(右下角,3s 自动消失,点击淡出) -->
    <AlertNotify />
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 248px 1fr;
  height: 100vh;
  overflow: hidden;
}
/* 拖动期间禁用文本选中与过渡,跟随更平滑 */
.shell.is-resizing {
  user-select: none;
}
.shell.is-resizing .sidebar,
.shell.is-resizing .pane {
  transition: none !important;
}

/* ============================================================
   侧边栏
   ============================================================ */
.sidebar {
  background: var(--paper-deep);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 30px 22px 22px;
  position: relative;
  transition: width 0.05s linear;
}
.sidebar::before {
  /* 左上角微辉光,呼应深空主题 */
  content: '';
  position: absolute;
  inset: 0 0 auto 0;
  height: 220px;
  background: radial-gradient(420px 220px at 0% 0%, var(--glow-1), transparent 70%);
  pointer-events: none;
}
.sidebar::after {
  content: '';
  position: absolute;
  right: 0;
  top: 28%;
  bottom: 28%;
  width: 1px;
  background: linear-gradient(transparent, var(--line-strong), transparent);
  pointer-events: none;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 6px 30px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
  position: relative;
}
.brand-mark {
  width: 34px;
  height: 34px;
  position: relative;
  flex-shrink: 0;
  display: grid;
  place-items: center;
}
.brand-mark-core {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, var(--sage) 0%, var(--sage-deep) 75%);
  box-shadow: 0 0 14px var(--sage-soft);
  position: relative;
  z-index: 2;
}
.brand-mark-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid var(--line-strong);
  animation: ring-spin 12s linear infinite;
}
.brand-mark-ring::after {
  content: '';
  position: absolute;
  top: -3px;
  left: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--sage);
  box-shadow: 0 0 8px var(--sage);
  transform: translateX(-50%);
}
@keyframes ring-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.brand-name {
  font-size: 26px;
  line-height: 1;
  font-weight: 500;
}
.brand-sub {
  margin-top: 4px;
  color: var(--ink-3);
  font-size: 11px;
}

.nav-section-label {
  padding: 0 14px 10px;
  color: var(--ink-3);
  font-size: 11px;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  overflow-y: auto;
}
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius);
  color: var(--ink-3);
  transition: color 0.25s var(--ease), background 0.25s var(--ease), border-color 0.25s var(--ease);
  border: 1px solid transparent;
  cursor: grab;
}
.nav-item:active {
  cursor: grabbing;
}
.nav-item:hover {
  color: var(--ink);
  background: var(--sage-tint);
}
.nav-icon {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 5px;
  background: var(--surface);
  border: 1px solid var(--line);
  color: var(--ink-3);
  transition: all 0.25s var(--ease);
  flex-shrink: 0;
}
.nav-item:hover .nav-icon,
.nav-item.active .nav-icon {
  color: var(--sage);
  border-color: var(--sage);
  background: var(--sage-soft);
  box-shadow: 0 0 0 3px var(--sage-tint);
}
.nav-idx {
  font-size: 11px;
  color: var(--ink-5);
  letter-spacing: 0.06em;
  width: 16px;
  transition: color 0.25s var(--ease);
}
.nav-label {
  font-size: 13.5px;
  font-weight: 500;
  letter-spacing: 0.01em;
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-bar {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%) scaleY(0);
  width: 3px;
  height: 22px;
  background: linear-gradient(var(--sage), var(--sage-deep));
  border-radius: 0 3px 3px 0;
  transition: transform 0.3s var(--ease);
  box-shadow: 0 0 12px var(--sage-soft);
}
.nav-grip {
  color: var(--ink-5);
  opacity: 0;
  transition: opacity 0.25s var(--ease);
  display: grid;
  place-items: center;
}
.nav-item:hover .nav-grip {
  opacity: 1;
}
.nav-item.active {
  color: var(--ink);
  background: var(--surface);
  border-color: var(--line);
}
.nav-item.active .nav-idx {
  color: var(--sage);
}
.nav-item.active .nav-bar {
  transform: translateY(-50%) scaleY(1);
}
.nav-item.is-split-target {
  border-color: var(--sage);
  box-shadow: 0 0 0 2px var(--sage-tint);
}
.nav-item.is-primary-split::after {
  content: '主';
  position: absolute;
  top: 6px;
  right: 8px;
  font-size: 8px;
  font-family: var(--font-mono);
  letter-spacing: 0.08em;
  color: var(--ink-4);
  background: var(--paper-deep);
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  padding: 1px 4px;
  line-height: 1.3;
}

.side-foot {
  border-top: 1px solid var(--line);
  padding-top: 18px;
  margin-top: 12px;
}
.user-block {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--sage), var(--sage-deep));
  color: #06141a;
  display: grid;
  place-items: center;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
  flex-shrink: 0;
  box-shadow: 0 0 0 3px var(--sage-soft), 0 6px 16px rgba(0, 0, 0, 0.25);
}
.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink);
}
.user-role {
  color: var(--ink-3);
  font-size: 11px;
  text-transform: uppercase;
  margin-top: 2px;
}
.logout {
  width: 100%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid var(--line-strong);
  background: transparent;
  border-radius: var(--radius);
  padding: 9px;
  color: var(--ink-3);
  font-size: 12px;
  letter-spacing: 0.04em;
  transition: all 0.2s var(--ease);
  cursor: pointer;
}
.logout:hover {
  border-color: var(--terra);
  color: var(--terra);
  background: rgba(239, 107, 126, 0.06);
}

/* —— 侧边栏缩放手柄 —— */
.sidebar-resizer {
  position: absolute;
  top: 0;
  right: -3px;
  width: 7px;
  height: 100%;
  cursor: col-resize;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
}
.resizer-grip {
  width: 2px;
  height: 38px;
  border-radius: 2px;
  background: var(--line-strong);
  opacity: 0.4;
  transition: all 0.2s var(--ease);
}
.sidebar-resizer:hover .resizer-grip {
  background: var(--sage);
  opacity: 1;
  height: 56px;
  box-shadow: 0 0 12px var(--sage-soft);
}
.sidebar-resizer:active .resizer-grip {
  background: var(--sage-deep);
  height: 72px;
}

/* ============================================================
   主区
   ============================================================ */
.main {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  min-width: 0;
}
.main.drag-over .content-wrap {
  /* 拖拽 hover 时主区轻微抬升,提示可放置 */
  filter: saturate(1.08);
}
.main.split-on .pane-primary {
  /* 拆分开启后主面板可缩窄 */
  flex: 1 1 auto;
  min-width: 0;
}

.topbar {
  height: 72px;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 40px;
  background: color-mix(in srgb, var(--paper) 78%, transparent);
  backdrop-filter: blur(12px) saturate(1.2);
  -webkit-backdrop-filter: blur(12px) saturate(1.2);
  position: relative;
  z-index: 5;
}
.topbar::after {
  /* 顶栏下方淡渐变线 */
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--line-strong), transparent);
}
.page-title-wrap {
  display: flex;
  align-items: center;
  gap: 14px;
}
.page-glyph {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--sage);
  background: var(--sage-soft);
  border: 1px solid var(--line-strong);
  box-shadow: 0 0 0 4px var(--sage-tint);
}
.page-eyebrow {
  font-size: 11px;
  color: var(--ink-4);
  margin-bottom: 3px;
}
.page-title {
  font-size: 24px;
  font-weight: 400;
  letter-spacing: -0.01em;
  line-height: 1;
}
.top-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 12px;
  border-radius: var(--radius);
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink-2);
  font-size: 12px;
  font-family: var(--font-sans);
  cursor: pointer;
  transition: all 0.2s var(--ease);
}
.ghost-btn:hover {
  border-color: var(--sage);
  color: var(--sage);
  background: var(--sage-tint);
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

/* ============================================================
   内容区 + 拆分面板
   ============================================================ */
.content-wrap {
  flex: 1;
  display: flex;
  align-items: stretch;
  overflow: hidden;
  position: relative;
  min-height: 0;
}
.pane {
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  overflow: hidden;
}
.pane-primary {
  flex: 1 1 auto;
}
.pane-split {
  flex: 0 0 50%;
  border-left: 1px solid var(--line);
  background: color-mix(in srgb, var(--paper) 50%, var(--paper-deep));
  animation: pane-in 0.32s var(--ease) both;
}
@keyframes pane-in {
  from { opacity: 0; transform: translateX(16px); }
  to   { opacity: 1; transform: translateX(0); }
}
.pane-tag {
  position: absolute;
  top: 12px;
  right: 16px;
  font-size: 11px;
  color: var(--ink-5);
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 2px 7px;
  border-radius: 3px;
  z-index: 3;
  pointer-events: none;
}
.pane-tag.split {
  position: static;
  background: var(--sage-soft);
  color: var(--sage-deep);
  border-color: var(--sage);
}
.pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--paper) 70%, transparent);
}
.pane-head-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pane-split-title {
  font-size: 16px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
}
.pane-split-ico {
  color: var(--sage);
}
.pane-close {
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: 6px;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  color: var(--ink-3);
  cursor: pointer;
  transition: all 0.2s var(--ease);
}
.pane-close:hover {
  color: var(--terra);
  border-color: var(--terra);
  background: rgba(239, 107, 126, 0.06);
}
.pane-split-body {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px 40px;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 34px 40px 48px;
}

/* —— 分隔条 —— */
.split-divider {
  flex: 0 0 9px;
  cursor: col-resize;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  z-index: 4;
}
.split-divider::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 1px;
  background: var(--line);
  transform: translateX(-50%);
  transition: background 0.2s var(--ease), width 0.2s var(--ease);
}
.split-divider:hover::before,
.split-divider:active::before {
  background: var(--sage);
  width: 2px;
  box-shadow: 0 0 12px var(--sage-soft);
}
.split-divider-grip {
  width: 3px;
  height: 36px;
  border-radius: 3px;
  background: var(--line-strong);
  opacity: 0.5;
  transition: all 0.2s var(--ease);
  position: relative;
  z-index: 2;
}
.split-divider:hover .split-divider-grip,
.split-divider:active .split-divider-grip {
  background: var(--sage);
  opacity: 1;
  height: 56px;
}

/* —— 拖拽 drop 提示 —— */
.drop-hint {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, var(--paper) 60%, transparent);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  pointer-events: none;
  animation: drop-fade 0.18s var(--ease) both;
}
@keyframes drop-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}
.drop-hint-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 28px 44px;
  border: 2px dashed var(--sage);
  border-radius: 16px;
  background: color-mix(in srgb, var(--surface) 80%, transparent);
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.35), 0 0 0 6px var(--sage-tint);
  animation: drop-pop 0.22s var(--ease) both;
}
@keyframes drop-pop {
  from { transform: scale(0.94); }
  to   { transform: scale(1); }
}
.drop-hint-glyph {
  color: var(--sage);
  filter: drop-shadow(0 0 12px var(--sage-soft));
  animation: ring-spin 4s linear infinite;
}
.drop-hint-title {
  font-size: 20px;
  font-weight: 500;
  color: var(--ink);
}
.drop-hint-sub {
  color: var(--ink-3);
  font-size: 12px;
}
</style>
