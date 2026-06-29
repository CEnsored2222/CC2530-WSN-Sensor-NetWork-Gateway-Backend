<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { getSocket } from '@/ws/socket'

// 通报队列(右下角堆叠)
const toasts = ref([])

const SEV_META = {
  info:     { label: '信息', tone: 'info',     sym: '◇' },
  warning:  { label: '警告', tone: 'warning',  sym: '▲' },
  critical: { label: '严重', tone: 'critical', sym: '✕' }
}

function fmtVal(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(1)
}

function push(payload) {
  const id = Date.now() + Math.random()
  const meta = SEV_META[payload.severity] || SEV_META.info
  const toast = { id, payload, meta, leaving: false, timer: null }
  // 固定 3s 后自动淡出消失
  toast.timer = setTimeout(() => dismiss(id), 3000)
  toasts.value.push(toast)
  // 队列最多保留 4 条,超出移除最早的
  if (toasts.value.length > 4) {
    const first = toasts.value.shift()
    if (first.timer) clearTimeout(first.timer)
  }
}

// 用户点击:逐渐淡出消失
function dismiss(id) {
  const t = toasts.value.find((x) => x.id === id)
  if (!t || t.leaving) return
  t.leaving = true
  if (t.timer) clearTimeout(t.timer)
  // 等待淡出动画结束后移除 DOM
  setTimeout(() => {
    toasts.value = toasts.value.filter((x) => x.id !== id)
  }, 320)
}

let socket = null
function bind() {
  socket = getSocket()
  socket.off('alert_notify').on('alert_notify', push)
}
function unbind() {
  if (socket) socket.off('alert_notify')
  toasts.value.forEach((t) => t.timer && clearTimeout(t.timer))
  toasts.value = []
}

onMounted(bind)
onBeforeUnmount(unbind)

// 暴露给父组件手动触发(可选,用于测试)
defineExpose({ push, dismiss })
</script>

<template>
  <Teleport to="body">
    <div class="alert-notify-stack" aria-live="polite">
      <TransitionGroup name="an-toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="an-toast"
          :class="[`tone-${t.payload.severity || 'info'}`, { leaving: t.leaving }]"
          @click="dismiss(t.id)"
          title="点击关闭"
        >
          <div class="an-sym">{{ t.meta.sym }}</div>
          <div class="an-body">
            <div class="an-head">
              <span class="an-sev">{{ t.meta.label }}通报</span>
              <span class="an-rule">{{ t.payload.rule_name }}</span>
            </div>
            <div class="an-detail mono">
              <span class="an-metric">{{ t.payload.metric }}</span>
              <span class="an-val">{{ fmtVal(t.payload.value) }}</span>
              <span class="an-dev muted" v-if="t.payload.dev_mac">{{ t.payload.dev_mac }}</span>
            </div>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.alert-notify-stack {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column-reverse;
  gap: 12px;
  pointer-events: none;
}
.an-toast {
  pointer-events: auto;
  display: flex;
  align-items: stretch;
  gap: 14px;
  min-width: 300px;
  max-width: 380px;
  padding: 16px 18px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface-hi) 92%, transparent);
  border: 1px solid var(--line-strong);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.02);
  backdrop-filter: blur(12px) saturate(1.2);
  -webkit-backdrop-filter: blur(12px) saturate(1.2);
  cursor: pointer;
  transition: transform 0.32s var(--ease), opacity 0.32s var(--ease);
  position: relative;
  overflow: hidden;
}
.an-toast::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 3px 0 0 3px;
}
.tone-info::before    { background: var(--sage); }
.tone-warning::before { background: var(--amber); }
.tone-critical::before{ background: var(--terra); }

.an-sym {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  font-family: var(--font-display);
  font-size: 15px;
  flex-shrink: 0;
}
.tone-info .an-sym    { background: var(--sage-soft);  color: var(--sage-deep); }
.tone-warning .an-sym { background: var(--amber-soft); color: var(--amber); }
.tone-critical .an-sym{ background: #f7e6e1;           color: var(--terra); }

.an-body { min-width: 0; flex: 1; }
.an-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 6px;
}
.an-sev {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.tone-info .an-sev    { color: var(--sage-deep); }
.tone-warning .an-sev { color: var(--amber); }
.tone-critical .an-sev{ color: var(--terra); }
.an-rule {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.an-detail {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: var(--ink-3);
}
.an-metric {
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--ink-4);
}
.an-val {
  font-size: 16px;
  font-weight: 500;
  color: var(--ink);
}
.an-dev { font-size: 11px; }

/* —— 进入动画 —— */
.an-toast-enter-from {
  opacity: 0;
  transform: translateX(40px) scale(0.96);
}
.an-toast-leave-to {
  opacity: 0;
  transform: translateX(40px) scale(0.96);
}
.an-toast-enter-active,
.an-toast-leave-active {
  transition: opacity 0.32s var(--ease), transform 0.32s var(--ease);
}
/* 用户点击触发的逐渐淡出(更慢,营造"淡出"感) */
.an-toast.leaving {
  opacity: 0 !important;
  transform: translateX(20px) scale(0.98) !important;
  transition: opacity 0.3s var(--ease), transform 0.3s var(--ease);
}

/* hover 时微抬起,提示可点击 */
.an-toast:hover {
  transform: translateY(-2px);
}
</style>
