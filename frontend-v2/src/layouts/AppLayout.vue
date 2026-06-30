<script setup>
import { useRoute } from 'vue-router'
import FaultyTerminal from '@/components/vuebits/FaultyTerminal.vue'
import AuroraBackground from '@/components/layout/AuroraBackground.vue'
import GlassDock from '@/components/glass/GlassDock.vue'
import GlassTopbar from '@/components/glass/GlassTopbar.vue'

const route = useRoute()
</script>

<template>
  <div class="app-bg-terminal">
    <FaultyTerminal
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

  <AuroraBackground />

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
.app-bg-terminal {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}
.app-bg-terminal :deep(.faulty-terminal) {
  position: absolute;
  inset: 0;
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
