<script setup>
import { computed } from 'vue'

const props = defineProps({
  position: { type: String, default: 'bottom' }, // top | bottom | left | right
  divCount: { type: Number, default: 8 },
  blur: { type: Number, default: 8 },
  size: { type: String, default: '120px' },
  class: { type: String, default: '' }
})

const layers = computed(() => {
  const arr = []
  for (let i = 0; i < props.divCount; i++) {
    const t = (i + 1) / props.divCount
    // 越靠近边缘 blur 与不透明度越高,叠加形成渐变
    const opacity = Math.pow(t, 1.4)
    const blurAmount = props.blur * t
    arr.push({ opacity, blurAmount })
  }
  return arr
})

const isVertical = computed(() => props.position === 'top' || props.position === 'bottom')
const maskDirection = computed(() => {
  return {
    bottom: 'to top',
    top: 'to bottom',
    left: 'to right',
    right: 'to left'
  }[props.position] || 'to top'
})
</script>

<template>
  <div
    class="gradual-blur"
    :class="[`gradual-blur--${props.position}`, props.class]"
    :style="isVertical ? { height: props.size, left: 0, right: 0 } : { width: props.size, top: 0, bottom: 0 }"
    aria-hidden="true"
  >
    <div
      v-for="(layer, i) in layers"
      :key="i"
      class="gradual-blur__layer"
      :style="{
        opacity: layer.opacity,
        backdropFilter: `blur(${layer.blurAmount}px)`,
        WebkitBackdropFilter: `blur(${layer.blurAmount}px)`,
        maskImage: `linear-gradient(${maskDirection}, black 0%, transparent 100%)`,
        WebkitMaskImage: `linear-gradient(${maskDirection}, black 0%, transparent 100%)`
      }"
    />
  </div>
</template>

<style scoped>
.gradual-blur {
  position: absolute;
  z-index: 5;
  pointer-events: none;
}
.gradual-blur__layer {
  position: absolute;
  inset: 0;
}
.gradual-blur--bottom { bottom: 0; }
.gradual-blur--top { top: 0; }
.gradual-blur--left { left: 0; }
.gradual-blur--right { right: 0; }
</style>
