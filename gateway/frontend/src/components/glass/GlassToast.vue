<script setup>
import { useUiStore } from '@/stores/ui'
import Icon from '@/components/icons/Icon.vue'

const ui = useUiStore()

const iconMap = {
  success: 'check',
  warning: 'warning',
  danger: 'danger',
  info: 'info'
}

const colorMap = {
  success: { color: 'var(--mint)', bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)' },
  warning: { color: 'var(--amber-soft)', bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.3)' },
  danger: { color: 'var(--color-danger)', bg: 'rgba(248,113,113,0.12)', border: 'rgba(248,113,113,0.3)' },
  info: { color: 'var(--teal)', bg: 'rgba(20,184,166,0.12)', border: 'rgba(20,184,166,0.3)' }
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-6 right-6 z-[9999] flex flex-col gap-3 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="t in ui.toasts"
          :key="t.id"
          class="glass-heavy pointer-events-auto flex items-start gap-3 px-5 py-4 rounded-xl cursor-pointer min-w-[300px] max-w-[420px]"
          style="border: 1px solid; backdrop-filter: blur(28px) saturate(200%); box-shadow: 0 12px 40px rgba(0,0,0,0.4);"
          :style="{ borderColor: colorMap[t.type].border }"
          @click="ui.dismissToast(t.id)"
        >
          <div
            class="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center"
            :style="{ background: colorMap[t.type].bg, color: colorMap[t.type].color }"
          >
            <Icon :name="iconMap[t.type]" :size="18" />
          </div>
          <div class="flex-1 min-w-0">
            <p v-if="t.title" class="text-sm font-semibold" style="color: var(--text-primary)">{{ t.title }}</p>
            <p v-if="t.message" class="text-xs mt-0.5 break-words" style="color: var(--text-secondary)">{{ t.message }}</p>
          </div>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
