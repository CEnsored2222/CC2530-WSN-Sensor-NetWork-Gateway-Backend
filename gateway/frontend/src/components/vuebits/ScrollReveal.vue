<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

const props = defineProps({
  text: { type: String, required: true },
  tag: { type: String, default: 'p' },
  blur: { type: Number, default: 8 },
  threshold: { type: Number, default: 0.2 },
  stagger: { type: Number, default: 0.04 },
  duration: { type: Number, default: 0.8 },
  class: { type: String, default: '' }
})

const root = ref(null)
let tl = null
let refreshTimer = null

function build() {
  if (!root.value) return
  if (tl) {
    if (tl.scrollTrigger) tl.scrollTrigger.kill()
    tl.kill()
    tl = null
  }
  root.value.innerHTML = ''

  const words = props.text.split(/(\s+)/)
  words.forEach((w) => {
    if (/^\s+$/.test(w)) {
      root.value.appendChild(document.createTextNode(w))
      return
    }
    const span = document.createElement('span')
    span.className = 'reveal-word'
    span.style.display = 'inline-block'
    span.style.filter = `blur(${props.blur}px)`
    span.style.opacity = '0'
    span.style.willChange = 'filter, opacity'
    span.textContent = w
    root.value.appendChild(span)
  })

  const targets = root.value.querySelectorAll('.reveal-word')
  if (!targets.length) return

  tl = gsap.timeline({
    scrollTrigger: {
      trigger: root.value,
      start: `top ${Math.round((1 - props.threshold) * 100)}%`,
      once: true
    }
  })
  tl.to(targets, {
    opacity: 1,
    filter: 'blur(0px)',
    duration: props.duration,
    stagger: props.stagger,
    ease: 'expo.out'
  })

  // 不调用 ScrollTrigger.refresh() — 每次 refresh 会重算页面上所有触发器位置,
  // 导致正在播放的动画产生跳动(与 AnimatedContent/ShuffleText 相同的根因)。
  // 600ms 兜底:若文字仍不可见,直接渐显,不触发 refresh。
  refreshTimer = setTimeout(() => {
    if (root.value) {
      const stillHidden = root.value.querySelectorAll('.reveal-word[style*="opacity: 0"]')
      if (stillHidden.length) {
        gsap.to(targets, {
          opacity: 1,
          filter: 'blur(0px)',
          duration: 0.4,
          stagger: 0.02,
          ease: 'expo.out'
        })
      }
    }
  }, 600)
}

onMounted(build)
watch(() => props.text, build)
onBeforeUnmount(() => {
  if (refreshTimer) clearTimeout(refreshTimer)
  if (tl) {
    if (tl.scrollTrigger) tl.scrollTrigger.kill()
    tl.kill()
  }
})
</script>

<template>
  <component :is="tag" ref="root" :class="props.class" class="scroll-reveal" />
</template>

<style scoped>
.scroll-reveal {
  display: block;
}
</style>
