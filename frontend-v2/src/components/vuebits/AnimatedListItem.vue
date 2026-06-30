<script setup>
import { ref } from 'vue'
import { useInView } from 'motion-v'

const props = defineProps({
  delay: { type: Number, default: 0 },
  y: { type: Number, default: 24 },
  scale: { type: Number, default: 0.96 },
  duration: { type: Number, default: 0.5 },
  once: { type: Boolean, default: true },
  threshold: { type: Number, default: 0 }
})

const itemRef = ref(null)
const isInView = useInView(itemRef, {
  once: props.once,
  margin: '0px 0px -40px 0px'
})
</script>

<template>
  <div
    ref="itemRef"
    class="animated-list-item"
    :style="{
      opacity: isInView ? 1 : 0,
      transform: isInView ? 'translateY(0) scale(1)' : `translateY(${y}px) scale(${scale})`,
      transition: `opacity ${duration}s cubic-bezier(0.25, 0.46, 0.45, 0.94) ${delay}s, transform ${duration}s cubic-bezier(0.25, 0.46, 0.45, 0.94) ${delay}s`
    }"
  >
    <slot />
  </div>
</template>
