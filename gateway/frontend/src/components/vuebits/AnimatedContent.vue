<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

const props = defineProps({
  direction: { type: String, default: 'left' }, // left | right | up | down
  distance: { type: Number, default: 100 },
  duration: { type: Number, default: 1 },
  blur: { type: Boolean, default: false },
  delay: { type: Number, default: 0 },
  threshold: { type: Number, default: 0.15 },
  once: { type: Boolean, default: true },
  class: { type: String, default: '' }
})

const root = ref(null)
let tween = null
let refreshTimer = null

const offsetMap = {
  left: { x: -props.distance, y: 0 },
  right: { x: props.distance, y: 0 },
  up: { x: 0, y: props.distance },
  down: { x: 0, y: -props.distance }
}

onMounted(() => {
  if (!root.value) return
  const from = {
    ...offsetMap[props.direction] || offsetMap.left,
    opacity: 0
  }
  if (props.blur) from.filter = 'blur(12px)'

  tween = gsap.fromTo(root.value, from, {
    x: 0,
    y: 0,
    opacity: 1,
    filter: 'blur(0px)',
    duration: props.duration,
    delay: props.delay,
    ease: 'expo.out',
    onComplete: () => {
      if (root.value) root.value.style.willChange = 'auto'
    },
    scrollTrigger: {
      trigger: root.value,
      start: `top ${Math.round((1 - props.threshold) * 100)}%`,
      once: props.once
    }
  })

  // 不再调用 ScrollTrigger.refresh() — 每次 refresh 会重算页面上所有触发器位置,
  // 导致正在播放的动画产生跳动(多组件场景下连续 refresh 造成"先渲染→跳动→重渲染")。
  // GSAP scrollTrigger 在创建时会自动检测元素是否已在视口内并触发 onEnter。
  // 600ms 兜底:若元素仍不可见(ScrollTrigger 未触发),直接强制可见,不触发 refresh。
  refreshTimer = setTimeout(() => {
    if (root.value && gsap.getProperty(root.value, 'opacity') === 0) {
      gsap.set(root.value, { opacity: 1, x: 0, y: 0, filter: 'none' })
    }
    if (root.value) root.value.style.willChange = 'auto'
  }, 600)
})

onBeforeUnmount(() => {
  if (tween) tween.kill()
  if (refreshTimer) clearTimeout(refreshTimer)
})
</script>

<template>
  <div ref="root" :class="props.class" class="animated-content">
    <slot />
  </div>
</template>

<style scoped>
.animated-content {
  /* will-change set dynamically during animation, removed on complete */
}
</style>
