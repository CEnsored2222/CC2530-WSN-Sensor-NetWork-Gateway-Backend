<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import Icon from '@/components/icons/Icon.vue'

const route = useRoute()
const userStore = useUserStore()

const navItems = computed(() => {
  const items = [
    { name: 'home', label: '总览', icon: 'home', path: '/' },
    { name: 'devices', label: '设备', icon: 'devices', path: '/devices' },
    { name: 'history', label: '历史', icon: 'history', path: '/history' },
    { name: 'alerts', label: '告警', icon: 'bell', path: '/alerts' },
    { name: 'prediction', label: '预测', icon: 'chart', path: '/prediction' },
    { name: 'vision', label: '视觉', icon: 'eye', path: '/vision' }
  ]
  if (userStore.isAdmin) {
    items.push({ name: 'subscription', label: '订阅', icon: 'subscription', path: '/admin/subscription' })
    items.push({ name: 'logs', label: '日志', icon: 'logs', path: '/admin/logs' })
  }
  return items
})

const hovered = ref(null)
</script>

<template>
  <nav class="dock">
    <div class="dock-pill glass-liquid">
      <RouterLink
        v-for="item in navItems"
        :key="item.name"
        :to="item.path"
        class="dock-item"
        :class="{ 'dock-item--active': route.name === item.name }"
        data-cursor-target
        @mouseenter="hovered = item.name"
        @mouseleave="hovered = null"
      >
        <Icon
          :name="item.icon"
          :size="20"
          class="dock-icon"
        />
        <span v-if="hovered === item.name" class="dock-tooltip glass-liquid">{{ item.label }}</span>
      </RouterLink>
    </div>
  </nav>
</template>

<style scoped>
.dock {
  position: fixed;
  left: 22px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 50;
}
.dock-pill {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 8px;
}
.dock-item {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  transition: background 0.2s ease;
  text-decoration: none;
}
.dock-item--active {
  background: rgba(132, 204, 22, 0.14);
  box-shadow: inset 0 0 0 1px rgba(132, 204, 22, 0.20);
}
.dock-icon {
  transition: transform 0.2s ease, color 0.2s ease;
  color: var(--text-tertiary);
}
.dock-item--active .dock-icon {
  color: var(--mint);
  transform: scale(1.1);
}
.dock-item:hover .dock-icon {
  color: var(--text-primary);
}
.dock-tooltip {
  position: absolute;
  left: 100%;
  top: 50%;
  transform: translateY(-50%);
  margin-left: 10px;
  padding: 5px 10px;
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
  color: var(--text-primary);
  border-radius: 8px;
  pointer-events: none;
}
@media (max-width: 768px) {
  .dock {
    left: 12px;
  }
  .dock-item {
    width: 36px;
    height: 36px;
  }
}
</style>
