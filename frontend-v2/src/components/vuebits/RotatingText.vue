<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'

const props = defineProps({
  words: { type: Array, required: true },
  interval: { type: Number, default: 3000 },
  duration: { type: Number, default: 0.5 },
  class: { type: String, default: '' }
})

const currentIndex = ref(0)
const isAnimating = ref(false)
let timer = null

const current = computed(() => props.words[currentIndex.value] || '')

onMounted(() => {
  if (props.words.length <= 1) return
  timer = setInterval(() => {
    isAnimating.value = true
    setTimeout(() => {
      currentIndex.value = (currentIndex.value + 1) % props.words.length
      isAnimating.value = false
    }, props.duration * 1000 / 2)
  }, props.interval)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <span :class="props.class" class="rotating-text">
    <Transition name="rotate" mode="out-in">
      <span :key="currentIndex" class="rotating-word">{{ current }}</span>
    </Transition>
  </span>
</template>

<style scoped>
.rotating-text {
  display: inline-block;
  position: relative;
  vertical-align: bottom;
}
.rotating-word {
  display: inline-block;
  transform-origin: center bottom;
}

.rotate-enter-active,
.rotate-leave-active {
  transition: opacity var(--dur, 0.5s) ease, transform var(--dur, 0.5s) cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.rotate-enter-from {
  opacity: 0;
  transform: rotateX(-90deg) translateY(8px);
}
.rotate-leave-to {
  opacity: 0;
  transform: rotateX(90deg) translateY(-8px);
}
</style>
