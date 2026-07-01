<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  text: { type: String, required: true },
  speed: { type: Number, default: 50 },
  maxIterations: { type: Number, default: 8 },
  trigger: { type: String, default: 'view' },
  class: { type: String, default: '' }
})

const root = ref(null)
const display = ref('')
const isAnimating = ref(false)
let interval = null
let observer = null
let started = false
const pool = '!<>-_\\/[]{}—=+*^?#$%'

function isInViewport() {
  if (!root.value) return false
  const r = root.value.getBoundingClientRect()
  const vh = window.innerHeight || document.documentElement.clientHeight
  const vw = window.innerWidth || document.documentElement.clientWidth
  return r.width > 0 && r.height > 0 && r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0
}

onMounted(() => {
  // 先占位真实文本(避免布局抖动),动画开始后会替换为乱码再逐位解密
  display.value = props.text

  if (props.trigger === 'view') {
    // 同步视口检测:通过 v-if/条件渲染挂载时元素往往已在视口内,
    // IntersectionObserver 异步回调可能导致动画不触发,这里立即开跑。
    if (isInViewport()) {
      requestAnimationFrame(() => start())
      return
    }
    observer = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) start()
      })
    }, { threshold: 0.5 })
    if (root.value) observer.observe(root.value)
  }
})

watch(() => props.text, () => {
  display.value = props.text
  if (props.trigger === 'view' && started) start()
})

function start() {
  if (isAnimating.value) return
  started = true
  isAnimating.value = true

  const target = props.text
  let iteration = 0

  if (interval) clearInterval(interval)
  interval = setInterval(() => {
    display.value = target.split('').map((char, idx) => {
      if (idx < iteration) return target[idx]
      if (char === ' ' || char === '·' || char === '-') return char
      return pool[Math.floor(Math.random() * pool.length)]
    }).join('')

    if (iteration >= target.length) {
      clearInterval(interval)
      display.value = target
      isAnimating.value = false
    }
    iteration += 1 / 2
  }, props.speed)
}

defineExpose({ start })

onBeforeUnmount(() => {
  if (interval) clearInterval(interval)
  if (observer) observer.disconnect()
})
</script>

<template>
  <span ref="root" :class="props.class" class="decrypted-text" @mouseenter="trigger === 'hover' && start()">{{ display }}</span>
</template>

<style scoped>
.decrypted-text {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
</style>
