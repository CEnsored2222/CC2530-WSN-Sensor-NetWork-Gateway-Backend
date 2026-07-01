<script setup>
import Icon from '@/components/icons/Icon.vue'
import DotField from '@/components/vuebits/DotField.vue'

defineProps({
  icon: { type: String, default: 'info' },
  title: { type: String, default: '暂无数据' },
  description: { type: String, default: '' },
  decorative: { type: Boolean, default: true }
})
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 text-center relative">
    <div v-if="decorative" class="empty-dot-field">
      <DotField :gap="40" :proximity="60" :radius="50" />
    </div>
    <div class="relative mb-5">
      <div class="absolute inset-0 blur-2xl opacity-30" style="background: radial-gradient(circle, var(--mint), transparent 70%)" />
      <div class="relative w-16 h-16 rounded-2xl flex items-center justify-center" style="background: rgba(52,211,153,0.08); color: var(--mint); border: 1px solid var(--glass-border)">
        <Icon :name="icon" :size="28" />
      </div>
    </div>
    <p class="text-base font-semibold font-display" style="color: var(--text-secondary)">{{ title }}</p>
    <p v-if="description" class="mt-1.5 text-sm max-w-xs" style="color: var(--text-tertiary)">{{ description }}</p>
    <div class="mt-5">
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.empty-dot-field {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.35;
  pointer-events: none;
  overflow: hidden;
}
.empty-dot-field :deep(.dot-field-root) {
  position: absolute;
  inset: 0;
}
</style>
