<script setup>
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { SplitText as GSAPSplitText } from 'gsap/SplitText'
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'

gsap.registerPlugin(ScrollTrigger, GSAPSplitText)

const props = defineProps({
  text: { type: String, required: true },
  class: { type: String, default: '' },
  shuffleDirection: { type: String, default: 'right' },
  duration: { type: Number, default: 0.35 },
  maxDelay: { type: Number, default: 0 },
  ease: { type: [String, Function], default: 'power3.out' },
  threshold: { type: Number, default: 0.1 },
  rootMargin: { type: String, default: '-100px' },
  tag: { type: String, default: 'span' },
  textAlign: { type: String, default: 'left' },
  shuffleTimes: { type: Number, default: 1 },
  animationMode: { type: String, default: 'evenodd' },
  loop: { type: Boolean, default: false },
  loopDelay: { type: Number, default: 0 },
  stagger: { type: Number, default: 0.03 },
  scrambleCharset: { type: String, default: '' },
  colorFrom: { type: String, default: undefined },
  colorTo: { type: String, default: undefined },
  triggerOnce: { type: Boolean, default: true },
  respectReducedMotion: { type: Boolean, default: true },
  triggerOnHover: { type: Boolean, default: true }
})

const elRef = ref(null)
const fontsLoaded = ref(false)
const ready = ref(false)

const splitRef = ref(null)
const wrappersRef = ref([])
const tlRef = ref(null)
const playingRef = ref(false)
const hoverHandlerRef = ref(null)
const stRef = ref(null)
let refreshTimer = null

const scrollTriggerStart = computed(() => {
  const startPct = (1 - props.threshold) * 100
  const mm = /^(-?\d+(?:\.\d+)?)(px|em|rem|%)?$/.exec(props.rootMargin || '')
  const mv = mm ? parseFloat(mm[1]) : 0
  const mu = mm ? mm[2] || 'px' : 'px'
  const sign = mv === 0 ? '' : mv < 0 ? `-=${Math.abs(mv)}${mu}` : `+=${mv}${mu}`
  return `top ${startPct}%${sign}`
})

const classes = computed(() => {
  const base = 'shuffle-root inline-block whitespace-normal break-words will-change-transform leading-none'
  const visibility = ready.value ? 'visible' : 'invisible'
  return [base, visibility, props.class].filter(Boolean).join(' ')
})

const commonStyle = computed(() => ({
  textAlign: props.textAlign
}))

function rand(set) {
  return set.charAt(Math.floor(Math.random() * set.length)) || ''
}

function removeHover() {
  if (hoverHandlerRef.value && elRef.value) {
    elRef.value.removeEventListener('mouseenter', hoverHandlerRef.value)
    hoverHandlerRef.value = null
  }
}

function teardown() {
  if (tlRef.value) {
    tlRef.value.kill()
    tlRef.value = null
  }
  if (wrappersRef.value.length) {
    wrappersRef.value.forEach(wrap => {
      const inner = wrap.firstElementChild
      const orig = inner?.querySelector('[data-orig="1"]')
      if (orig && wrap.parentNode) wrap.parentNode.replaceChild(orig, wrap)
    })
    wrappersRef.value = []
  }
  try { splitRef.value?.revert() } catch { /* ignore */ }
  splitRef.value = null
  playingRef.value = false
}

function getInners() {
  return wrappersRef.value.map(w => w.firstElementChild)
}

function randomizeScrambles() {
  if (!props.scrambleCharset) return
  wrappersRef.value.forEach(w => {
    const strip = w.firstElementChild
    if (!strip) return
    const kids = Array.from(strip.children)
    for (let i = 1; i < kids.length - 1; i++) {
      kids[i].textContent = props.scrambleCharset.charAt(Math.floor(Math.random() * props.scrambleCharset.length))
    }
  })
}

function cleanupToStill() {
  wrappersRef.value.forEach(w => {
    const strip = w.firstElementChild
    if (!strip) return
    const real = strip.querySelector('[data-orig="1"]')
    if (!real) return
    strip.replaceChildren(real)
    strip.style.transform = 'none'
    strip.style.willChange = 'auto'
  })
}

function build() {
  if (!elRef.value) return
  teardown()

  const el = elRef.value
  const computedFont = getComputedStyle(el).fontFamily

  splitRef.value = new GSAPSplitText(el, {
    type: 'chars',
    charsClass: 'shuffle-char',
    wordsClass: 'shuffle-word',
    linesClass: 'shuffle-line',
    smartWrap: true,
    reduceWhiteSpace: false
  })

  const chars = (splitRef.value.chars || [])
  wrappersRef.value = []

  const rolls = Math.max(1, Math.floor(props.shuffleTimes))

  chars.forEach(ch => {
    const parent = ch.parentElement
    if (!parent) return

    const rect = ch.getBoundingClientRect()
    const w = rect.width
    const h = rect.height
    if (!w) return

    const isVertical = props.shuffleDirection === 'up' || props.shuffleDirection === 'down'

    const wrap = document.createElement('span')
    wrap.className = 'shuffle-wrap inline-block overflow-hidden text-left'
    Object.assign(wrap.style, {
      width: `${w}px`,
      height: isVertical ? `${h}px` : 'auto',
      verticalAlign: 'bottom'
    })

    const inner = document.createElement('span')
    inner.className = 'shuffle-inner inline-block will-change-transform origin-left transform-gpu ' +
      (isVertical ? 'whitespace-normal' : 'whitespace-nowrap')

    parent.insertBefore(wrap, ch)
    wrap.appendChild(inner)

    const firstOrig = ch.cloneNode(true)
    firstOrig.className = `text-left ${isVertical ? 'block' : 'inline-block'}`
    Object.assign(firstOrig.style, { width: `${w}px`, fontFamily: computedFont })

    ch.setAttribute('data-orig', '1')
    ch.className = `text-left ${isVertical ? 'block' : 'inline-block'}`
    Object.assign(ch.style, { width: `${w}px`, fontFamily: computedFont })

    inner.appendChild(firstOrig)

    for (let k = 0; k < rolls; k++) {
      const c = ch.cloneNode(true)
      if (props.scrambleCharset) c.textContent = rand(props.scrambleCharset)
      c.className = `text-left ${isVertical ? 'block' : 'inline-block'}`
      Object.assign(c.style, { width: `${w}px`, fontFamily: computedFont })
      inner.appendChild(c)
    }
    inner.appendChild(ch)

    const steps = rolls + 1

    let startX = 0, finalX = 0, startY = 0, finalY = 0

    if (props.shuffleDirection === 'right') {
      startX = -steps * w; finalX = 0
    } else if (props.shuffleDirection === 'left') {
      startX = 0; finalX = -steps * w
    } else if (props.shuffleDirection === 'down') {
      startY = -steps * h; finalY = 0
    } else if (props.shuffleDirection === 'up') {
      startY = 0; finalY = -steps * h
    }

    if (props.shuffleDirection === 'right' || props.shuffleDirection === 'down') {
      const firstCopy = inner.firstElementChild
      const real = inner.lastElementChild
      if (real) inner.insertBefore(real, inner.firstChild)
      if (firstCopy) inner.appendChild(firstCopy)
    }

    if (!isVertical) {
      gsap.set(inner, { x: startX, y: 0, force3D: true })
      inner.setAttribute('data-start-x', String(startX))
      inner.setAttribute('data-final-x', String(finalX))
    } else {
      gsap.set(inner, { x: 0, y: startY, force3D: true })
      inner.setAttribute('data-start-y', String(startY))
      inner.setAttribute('data-final-y', String(finalY))
    }

    if (props.colorFrom) inner.style.color = props.colorFrom

    wrappersRef.value.push(wrap)
  })
}

function play() {
  const strips = getInners()
  if (!strips.length) return

  playingRef.value = true
  const isVertical = props.shuffleDirection === 'up' || props.shuffleDirection === 'down'

  const tl = gsap.timeline({
    smoothChildTiming: true,
    repeat: props.loop ? -1 : 0,
    repeatDelay: props.loop ? props.loopDelay : 0,
    onRepeat: () => {
      if (props.scrambleCharset) randomizeScrambles()
      if (isVertical) {
        gsap.set(strips, { y: (_i, t) => parseFloat(t.getAttribute('data-start-y') || '0') })
      } else {
        gsap.set(strips, { x: (_i, t) => parseFloat(t.getAttribute('data-start-x') || '0') })
      }
    },
    onComplete: () => {
      playingRef.value = false
      if (!props.loop) {
        cleanupToStill()
        if (props.colorTo) gsap.set(strips, { color: props.colorTo })
        armHover()
      }
    }
  })

  const addTween = (targets, at) => {
    const dur = props.duration
    const ez = props.ease
    const staggerVal = props.stagger

    if (isVertical) {
      tl.to(targets, {
        y: (_i, t) => parseFloat(t.getAttribute('data-final-y') || '0'),
        duration: dur, ease: ez, force3D: true,
        stagger: props.animationMode === 'evenodd' ? staggerVal : 0
      }, at)
    } else {
      tl.to(targets, {
        x: (_i, t) => parseFloat(t.getAttribute('data-final-x') || '0'),
        duration: dur, ease: ez, force3D: true,
        stagger: props.animationMode === 'evenodd' ? staggerVal : 0
      }, at)
    }

    if (props.colorFrom && props.colorTo) {
      tl.to(targets, { color: props.colorTo, duration: dur, ease: ez }, at)
    }
  }

  if (props.animationMode === 'evenodd') {
    const odd = strips.filter((_el, i) => i % 2 === 1)
    const even = strips.filter((_el, i) => i % 2 === 0)
    const oddTotal = props.duration + Math.max(0, odd.length - 1) * props.stagger
    const evenStart = odd.length ? oddTotal * 0.7 : 0
    if (odd.length) addTween(odd, 0)
    if (even.length) addTween(even, evenStart)
  } else {
    strips.forEach(strip => {
      const d = Math.random() * props.maxDelay
      if (isVertical) {
        tl.to(strip, {
          y: parseFloat(strip.getAttribute('data-final-y') || '0'),
          duration: props.duration, ease: props.ease, force3D: true
        }, d)
      } else {
        tl.to(strip, {
          x: parseFloat(strip.getAttribute('data-final-x') || '0'),
          duration: props.duration, ease: props.ease, force3D: true
        }, d)
      }
      if (props.colorFrom && props.colorTo) {
        tl.fromTo(strip, { color: props.colorFrom }, { color: props.colorTo, duration: props.duration, ease: props.ease }, d)
      }
    })
  }

  tlRef.value = tl
}

function armHover() {
  if (!props.triggerOnHover || !elRef.value) return
  removeHover()
  const handler = () => {
    if (playingRef.value) return
    build()
    if (props.scrambleCharset) randomizeScrambles()
    play()
  }
  hoverHandlerRef.value = handler
  elRef.value.addEventListener('mouseenter', handler)
}

function create() {
  if (ready.value) return
  build()
  if (props.scrambleCharset) randomizeScrambles()
  play()
  armHover()
  ready.value = true
}

function initScrollTrigger() {
  if (!elRef.value) return

  stRef.value = ScrollTrigger.create({
    trigger: elRef.value,
    start: scrollTriggerStart.value,
    once: props.triggerOnce,
    onEnter: create
  })

  // 不调用 ScrollTrigger.refresh() — 每次 refresh 会重算页面上所有触发器位置,
  // 导致正在播放的动画产生跳动(与 AnimatedContent 相同的根因)。
  // 600ms 兜底:若 ScrollTrigger 未触发 onEnter(元素已在视口内),直接调用 create()。
  refreshTimer = setTimeout(() => {
    if (!ready.value && elRef.value) {
      create()
    }
  }, 600)
}

function destroyScrollTrigger() {
  stRef.value?.kill()
  stRef.value = null
  removeHover()
  teardown()
  ready.value = false
}

onMounted(() => {
  if ('fonts' in document) {
    if (document.fonts.status === 'loaded') {
      fontsLoaded.value = true
    } else {
      document.fonts.ready.then(() => { fontsLoaded.value = true })
    }
  } else {
    fontsLoaded.value = true
  }
})

watch(fontsLoaded, loaded => {
  if (loaded) initScrollTrigger()
})

watch(
  () => [props.text, props.duration, props.maxDelay, props.ease, scrollTriggerStart.value,
    fontsLoaded.value, props.shuffleDirection, props.shuffleTimes, props.animationMode,
    props.loop, props.loopDelay, props.stagger, props.scrambleCharset,
    props.colorFrom, props.colorTo, props.triggerOnce, props.respectReducedMotion, props.triggerOnHover],
  () => {
    if (!fontsLoaded.value) return
    destroyScrollTrigger()
    initScrollTrigger()
  }
)

onBeforeUnmount(() => {
  if (refreshTimer) clearTimeout(refreshTimer)
  destroyScrollTrigger()
})
</script>

<template>
  <component :is="tag" ref="elRef" :class="classes" :style="commonStyle">{{ text }}</component>
</template>

<style scoped>
.shuffle-root {
  display: inline-block;
}
.shuffle-wrap {
  display: inline-block;
  overflow: hidden;
  text-align: left;
}
.shuffle-inner {
  display: inline-block;
  will-change: transform;
  transform-origin: left center;
}
</style>
