<script setup>
import { RouterView } from 'vue-router'
import GlassToast from '@/components/glass/GlassToast.vue'
</script>

<template>
  <RouterView v-slot="{ Component }">
    <Transition name="route">
      <component :is="Component" />
    </Transition>
  </RouterView>
  <GlassToast />
</template>
