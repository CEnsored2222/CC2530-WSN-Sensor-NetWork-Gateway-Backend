<script setup>
defineProps({
  padding: { type: String, default: 'p-6' },
  hover: { type: Boolean, default: true },
  as: { type: String, default: 'div' }
})
</script>

<template>
  <component :is="as" class="glass-card glass-card-surface" :class="[padding, hover ? 'glass-card--hover' : '']">
    <slot />
  </component>
</template>

<style scoped>
.glass-card-surface {
  position: relative;
  border-radius: var(--radius-lg);
}
.glass-card--hover {
  cursor: default;
}
</style>
