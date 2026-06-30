<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { gsap } from 'gsap'

const props = defineProps({
  direction: { type: String, default: 'up' }, // up | down | left | right | none
  distance: { type: Number, default: 24 },
  blur: { type: Boolean, default: true },
  duration: { type: Number, default: 0.7 },
  delay: { type: Number, default: 0 },
  threshold: { type: Number, default: 0.2 },
  once: { type: Boolean, default: true },
  class: { type: String, default: '' }
})

const root = ref(null)
let tween = null
let observer = null

const offsetMap = {
  up: { y: props.distance },
  down: { y: -props.distance },
  left: { x: props.distance },
  right: { x: -props.distance },
  none: {}
}

onMounted(() => {
  if (!root.value) return
  const from = { opacity: 0, ...(offsetMap[props.direction] || offsetMap.up) }
  if (props.blur) from.filter = 'blur(8px)'

  gsap.set(root.value, from)

  observer = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) {
        if (root.value) root.value.style.willChange = 'transform, opacity, filter'
        tween = gsap.to(root.value, {
          opacity: 1,
          x: 0,
          y: 0,
          filter: 'blur(0px)',
          duration: props.duration,
          delay: props.delay,
          ease: 'expo.out',
          overwrite: true,
          onComplete: () => {
            if (root.value) root.value.style.willChange = 'auto'
          }
        })
        if (props.once) observer.disconnect()
      } else if (!props.once) {
        if (tween) tween.kill()
        gsap.set(root.value, from)
      }
    })
  }, { threshold: props.threshold })

  observer.observe(root.value)
})

onBeforeUnmount(() => {
  if (tween) tween.kill()
  if (observer) observer.disconnect()
})
</script>

<template>
  <div ref="root" :class="props.class" class="fade-content">
    <slot />
  </div>
</template>

<style scoped>
.fade-content {
  /* will-change 在动画开始前动态设置,完成后清除,避免常驻 GPU 内存占用 */
}
</style>
