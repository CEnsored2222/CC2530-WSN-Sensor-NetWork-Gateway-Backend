<script setup>
import { ref, watch, computed } from 'vue'
import { useThemeStore } from '@/stores/theme'
import Icon from '@/components/icons/Icon.vue'

const themeStore = useThemeStore()
const visible = ref(false)
const icon = ref('moon')
const animClass = ref('')

const glowColor = computed(() => icon.value === 'sun' ? '#fbbf24' : '#14b8a6')

watch(() => themeStore.theme, (to, from) => {
  if (!from) return
  icon.value = to === 'dark' ? 'moon' : 'sun'
  animClass.value = to === 'dark' ? 'tt-slide-down' : 'tt-slide-up'
  visible.value = true
  setTimeout(() => { visible.value = false }, 1000)
})
</script>

<template>
  <Transition name="tt-fade">
    <div v-if="visible" class="theme-transition" :class="animClass">
      <Icon :name="icon" :size="96" class="tt-icon" />
    </div>
  </Transition>
</template>

<style scoped>
.theme-transition {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  background: var(--bg-base);
}
.tt-icon {
  position: relative;
  z-index: 1;
}
.tt-slide-up .tt-icon {
  color: #fbbf24;
  animation: tt-icon-up 1.0s cubic-bezier(0.4, 0, 0.2, 1) both;
  filter: drop-shadow(0 0 60px rgba(251, 191, 36, 0.5));
}
.tt-slide-down .tt-icon {
  color: #14b8a6;
  animation: tt-icon-down 1.0s cubic-bezier(0.4, 0, 0.2, 1) both;
  filter: drop-shadow(0 0 60px rgba(20, 184, 166, 0.5));
}

@keyframes tt-icon-down {
  0%   { transform: translateY(-200px) scale(0.1); opacity: 0; }
  25%  { transform: translateY(0) scale(1.2); opacity: 1; }
  50%  { transform: translateY(0) scale(1); opacity: 1; }
  75%  { transform: translateY(60px) scale(0.4); opacity: 0.15; }
  100% { transform: translateY(200px) scale(0.1); opacity: 0; }
}
@keyframes tt-icon-up {
  0%   { transform: translateY(200px) scale(0.1); opacity: 0; }
  25%  { transform: translateY(0) scale(1.2); opacity: 1; }
  50%  { transform: translateY(0) scale(1); opacity: 1; }
  75%  { transform: translateY(-60px) scale(0.4); opacity: 0.15; }
  100% { transform: translateY(-200px) scale(0.1); opacity: 0; }
}

.tt-fade-enter-active { transition: opacity 0.1s ease; }
.tt-fade-leave-active { transition: opacity 0.2s ease; }
.tt-fade-enter-from,
.tt-fade-leave-to { opacity: 0; }
</style>

