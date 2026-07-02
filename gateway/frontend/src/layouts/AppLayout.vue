<script setup>
import { useRoute } from 'vue-router'
import { useThemeStore } from '@/stores/theme'
import FaultyTerminal from '@/components/vuebits/FaultyTerminal.vue'
import AuroraBackground from '@/components/layout/AuroraBackground.vue'
import ThemeTransition from '@/components/layout/ThemeTransition.vue'
import GlassDock from '@/components/glass/GlassDock.vue'
import GlassTopbar from '@/components/glass/GlassTopbar.vue'

const route = useRoute()
const themeStore = useThemeStore()
</script>

<template>
  <div class="bg-wrapper">
    <div class="bg-layer" :class="{ 'bg-layer--active': themeStore.theme === 'dark' }">
      <FaultyTerminal
        :pause="themeStore.theme !== 'dark'"
        :brightness="0.18"
        :tint="'#84cc16'"
        :scanline-intensity="0.2"
        :glitch-amount="0.5"
        :noise-amp="0.7"
        :curvature="0.1"
        :chromatic-aberration="0"
        :dither="true"
        :mouse-react="true"
        :mouse-strength="0.15"
        :page-load-animation="true"
        :time-scale="0.25"
      />
    </div>
    <div class="bg-layer" :class="{ 'bg-layer--active': themeStore.theme === 'light' }">
      <AuroraBackground />
    </div>
  </div>

  <ThemeTransition />

  <GlassTopbar />

  <main class="app-main">
    <RouterView v-slot="{ Component }">
      <Transition name="route">
        <component :is="Component" :key="route.path" />
      </Transition>
    </RouterView>
  </main>

  <GlassDock />
</template>

<style scoped>
.bg-wrapper {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.bg-layer {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.7s cubic-bezier(0.4, 0, 0.2, 1);
}
.bg-layer--active {
  opacity: 1;
}
.bg-layer :deep(.faulty-terminal) {
  position: absolute;
  inset: 0;
}
.bg-layer :deep(.aurora-background),
.bg-layer :deep(.aurora-background--fixed),
.bg-layer :deep(.aurora-blob),
.bg-layer :deep(.aurora-shape),
.bg-layer :deep(.aurora-line),
.bg-layer :deep(.aurora-noise-mid),
.bg-layer :deep(.aurora-grid) {
  position: absolute !important;
}
.app-main {
  position: relative;
  z-index: 10;
  min-height: 100vh;
  min-height: 100dvh;
  padding: 5.5rem 1.5rem 2rem 5.5rem;
  background: transparent;
}

@media (max-width: 768px) {
  .app-main {
    padding: 5rem 1rem 1.5rem 4.5rem;
  }
}
</style>
