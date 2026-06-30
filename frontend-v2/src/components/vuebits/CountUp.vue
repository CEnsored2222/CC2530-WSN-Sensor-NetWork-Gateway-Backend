<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  from: { type: Number, default: 0 },
  to: { type: Number, required: true },
  duration: { type: Number, default: 2 },
  decimals: { type: Number, default: 0 },
  separator: { type: String, default: ',' },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' }
})

const display = ref(props.from)
const root = ref(null)
let raf = null
let startTime = null
let startVal = props.from
let targetVal = props.to
let started = false
let obs = null

function animate() {
  if (raf) cancelAnimationFrame(raf)
  startTime = null
  function step(ts) {
    if (!startTime) startTime = ts
    const progress = Math.min((ts - startTime) / (props.duration * 1000), 1)
    const eased = 1 - Math.pow(1 - progress, 3)
    display.value = startVal + (targetVal - startVal) * eased
    if (progress < 1) {
      raf = requestAnimationFrame(step)
    }
  }
  raf = requestAnimationFrame(step)
}

function isInViewport() {
  if (!root.value) return false
  const r = root.value.getBoundingClientRect()
  const vh = window.innerHeight || document.documentElement.clientHeight
  const vw = window.innerWidth || document.documentElement.clientWidth
  // 元素与视口有重叠且自身有尺寸
  return r.width > 0 && r.height > 0 && r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0
}

onMounted(() => {
  // 通过 v-if 挂载时元素往往已在视口内,IntersectionObserver 回调是异步的,
  // 会导致先闪一下 0 再跳到目标值。这里同步检测视口,命中则立即开跑。
  if (isInViewport()) {
    started = true
    // 仍用 rAF 调度,确保 DOM 已绘制首帧(0)后再开始递增
    requestAnimationFrame(() => animate())
    return
  }
  obs = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting && !started) {
        started = true
        animate()
      }
    })
  }, { threshold: 0.3 })
  if (root.value) obs.observe(root.value)
})

watch(() => props.to, (newVal) => {
  startVal = display.value
  targetVal = newVal
  startTime = null
  animate()
})

function format(num) {
  const fixed = num.toFixed(props.decimals)
  const [int, dec] = fixed.split('.')
  const intStr = int.replace(/\B(?=(\d{3})+(?!\d))/g, props.separator)
  return props.prefix + (dec ? intStr + '.' + dec : intStr) + props.suffix
}

defineExpose({
  update(newVal) {
    startVal = display.value
    targetVal = newVal
    startTime = null
    animate()
  }
})

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  if (obs) obs.disconnect()
})
</script>

<template>
  <span ref="root" class="count-up data-value">{{ format(display) }}</span>
</template>

<style scoped>
.count-up {
  font-variant-numeric: tabular-nums;
}
</style>
