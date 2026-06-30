<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  text: { type: String, required: true },
  label: { type: String, default: '' },
  fromFontWeight: { type: Number, default: 400 },
  toFontWeight: { type: Number, default: 800 },
  class: { type: String, default: '' }
})

const root = ref(null)
const container = ref(null)

onMounted(() => {
  if (!container.value || !root.value) return
  if (window.matchMedia('(pointer: coarse)').matches) return

  const onMove = (e) => {
    const rect = container.value.getBoundingClientRect()
    const mouseX = e.clientX - rect.left
    const mouseY = e.clientY - rect.top

    const letters = root.value.querySelectorAll('.vp-letter')
    letters.forEach((letter) => {
      const lRect = letter.getBoundingClientRect()
      const lx = lRect.left - rect.left + lRect.width / 2
      const ly = lRect.top - rect.top + lRect.height / 2
      const dist = Math.sqrt((mouseX - lx) ** 2 + (mouseY - ly) ** 2)
      const maxDist = 180
      const proximity = Math.max(0, 1 - dist / maxDist)
      const wght = props.fromFontWeight + (props.toFontWeight - props.fromFontWeight) * proximity
      letter.style.setProperty('--font-wght', wght.toFixed(0))
    })
  }

  container.value.addEventListener('mousemove', onMove)
  onBeforeUnmount(() => {
    container.value?.removeEventListener('mousemove', onMove)
  })
})
</script>

<template>
  <div ref="container" class="vp-container">
    <span ref="root" :class="props.class" class="vp-text">
      <span
        v-for="(char, i) in text"
        :key="i"
        class="vp-letter font-variable"
        :style="{ '--font-wght': fromFontWeight }"
      >{{ char === ' ' ? '\u00A0' : char }}</span>
    </span>
  </div>
</template>

<style scoped>
.vp-container {
  display: inline-block;
}
.vp-text {
  display: inline-block;
}
.vp-letter {
  display: inline-block;
}
</style>
