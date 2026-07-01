<template>
  <div
    ref="containerRef"
    :class="[glassSurfaceClasses, focusVisibleClasses, props.className]"
    :style="containerStyles"
  >
    <svg
      class="glass-surface-svg"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <filter
          :id="filterId"
          color-interpolation-filters="sRGB"
          x="0%"
          y="0%"
          width="100%"
          height="100%"
        >
          <feImage
            ref="feImageRef"
            x="0"
            y="0"
            width="100%"
            height="100%"
            preserveAspectRatio="none"
            result="map"
          />
          <feDisplacementMap
            ref="redChannelRef"
            in="SourceGraphic"
            in2="map"
            result="dispRed"
          />
          <feColorMatrix
            in="dispRed"
            type="matrix"
            values="1 0 0 0 0
                    0 0 0 0 0
                    0 0 0 0 0
                    0 0 0 1 0"
            result="red"
          />
          <feDisplacementMap
            ref="greenChannelRef"
            in="SourceGraphic"
            in2="map"
            result="dispGreen"
          />
          <feColorMatrix
            in="dispGreen"
            type="matrix"
            values="0 0 0 0 0
                    0 1 0 0 0
                    0 0 0 0 0
                    0 0 0 1 0"
            result="green"
          />
          <feDisplacementMap
            ref="blueChannelRef"
            in="SourceGraphic"
            in2="map"
            result="dispBlue"
          />
          <feColorMatrix
            in="dispBlue"
            type="matrix"
            values="0 0 0 0 0
                    0 0 0 0 0
                    0 0 1 0 0
                    0 0 0 1 0"
            result="blue"
          />
          <feBlend in="red" in2="green" mode="screen" result="rg" />
          <feBlend in="rg" in2="blue" mode="screen" result="output" />
          <feGaussianBlur ref="gaussianBlurRef" in="output" stdDeviation="0.7" />
        </filter>
      </defs>
    </svg>
    <div class="glass-surface-content">
      <slot />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch, nextTick, onBeforeUnmount } from 'vue'

const props = defineProps({
  width: { type: [String, Number], default: '100%' },
  height: { type: [String, Number], default: '100%' },
  borderRadius: { type: Number, default: 20 },
  borderWidth: { type: Number, default: 0.07 },
  brightness: { type: Number, default: 70 },
  opacity: { type: Number, default: 0.93 },
  blur: { type: Number, default: 11 },
  displace: { type: Number, default: 0.5 },
  backgroundOpacity: { type: Number, default: 0 },
  saturation: { type: Number, default: 1 },
  distortionScale: { type: Number, default: -180 },
  redOffset: { type: Number, default: 0 },
  greenOffset: { type: Number, default: 10 },
  blueOffset: { type: Number, default: 20 },
  xChannel: { type: String, default: 'R' },
  yChannel: { type: String, default: 'G' },
  mixBlendMode: { type: String, default: 'difference' },
  className: { type: String, default: '' },
  style: { type: Object, default: () => ({}) },
  darkMode: { type: Boolean, default: null }
})

const isDarkMode = ref(false)
let darkModeCleanup = null

const updateDarkMode = () => {
  if (typeof window === 'undefined') return null
  if (props.darkMode !== null) {
    isDarkMode.value = props.darkMode
    return null
  }
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  isDarkMode.value = mediaQuery.matches
  const handler = (e) => {
    if (props.darkMode === null) isDarkMode.value = e.matches
  }
  mediaQuery.addEventListener('change', handler)
  return () => mediaQuery.removeEventListener('change', handler)
}

watch(() => props.darkMode, (val) => {
  if (val !== null) isDarkMode.value = val
})

const generateUniqueId = () => {
  return Math.random().toString(36).substring(2, 15)
}
const uniqueId = generateUniqueId()
const filterId = `glass-filter-${uniqueId}`
const redGradId = `red-grad-${uniqueId}`
const blueGradId = `blue-grad-${uniqueId}`

const containerRef = ref(null)
const feImageRef = ref(null)
const redChannelRef = ref(null)
const greenChannelRef = ref(null)
const blueChannelRef = ref(null)
const gaussianBlurRef = ref(null)
let resizeObserver = null

const generateDisplacementMap = () => {
  const rect = containerRef.value?.getBoundingClientRect?.()
  const actualWidth = rect?.width || 400
  const actualHeight = rect?.height || 200
  const edgeSize = Math.min(actualWidth, actualHeight) * (props.borderWidth * 0.5)
  const svgContent = `
    <svg viewBox="0 0 ${actualWidth} ${actualHeight}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="${redGradId}" x1="100%" y1="0%" x2="0%" y2="0%">
          <stop offset="0%" stop-color="#0000"/>
          <stop offset="100%" stop-color="red"/>
        </linearGradient>
        <linearGradient id="${blueGradId}" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stop-color="#0000"/>
          <stop offset="100%" stop-color="blue"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="${actualWidth}" height="${actualHeight}" fill="black"></rect>
      <rect x="0" y="0" width="${actualWidth}" height="${actualHeight}" rx="${props.borderRadius}" fill="url(#${redGradId})" />
      <rect x="0" y="0" width="${actualWidth}" height="${actualHeight}" rx="${props.borderRadius}" fill="url(#${blueGradId})" style="mix-blend-mode: ${props.mixBlendMode}" />
      <rect x="${edgeSize}" y="${edgeSize}" width="${actualWidth - edgeSize * 2}" height="${actualHeight - edgeSize * 2}" rx="${props.borderRadius}" fill="hsl(0 0% ${props.brightness}% / ${props.opacity})" style="filter:blur(${props.blur}px)" />
    </svg>
  `
  return `data:image/svg+xml,${encodeURIComponent(svgContent)}`
}

const updateDisplacementMap = () => {
  if (feImageRef.value) {
    feImageRef.value.setAttribute('href', generateDisplacementMap())
  }
}

const supportsSVGFilters = () => {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') return false
  const isWebkit = /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent)
  const isFirefox = /Firefox/.test(navigator.userAgent)
  if (isWebkit || isFirefox) {
    return false
  }
  const div = document.createElement('div')
  div.style.backdropFilter = `url(#${filterId})`
  return div.style.backdropFilter !== ''
}

const supportsBackdropFilter = () => {
  if (typeof window === 'undefined') return false
  return CSS.supports('backdrop-filter', 'blur(10px)')
}

const containerStyles = computed(() => {
  const baseStyles = {
    ...props.style,
    width: typeof props.width === 'number' ? `${props.width}px` : props.width,
    height: typeof props.height === 'number' ? `${props.height}px` : props.height,
    borderRadius: `${props.borderRadius}px`,
    '--glass-frost': props.backgroundOpacity,
    '--glass-saturation': props.saturation
  }
  const svgSupported = supportsSVGFilters()
  const backdropFilterSupported = supportsBackdropFilter()

  if (svgSupported) {
    return {
      ...baseStyles,
      background: isDarkMode.value
        ? `hsl(0 0% 0% / ${props.backgroundOpacity})`
        : `hsl(0 0% 100% / ${props.backgroundOpacity})`,
      backdropFilter: `url(#${filterId}) saturate(${props.saturation})`,
      WebkitBackdropFilter: `blur(${props.blur}px) saturate(${props.saturation})`,
      boxShadow: isDarkMode.value
        ? `0 0 2px 1px color-mix(in oklch, white, transparent 65%) inset,
           0 0 10px 4px color-mix(in oklch, white, transparent 85%) inset,
           0px 4px 16px rgba(17, 17, 26, 0.05),
           0px 8px 24px rgba(17, 17, 26, 0.05),
           0px 16px 56px rgba(17, 17, 26, 0.05),
           0px 4px 16px rgba(17, 17, 26, 0.05) inset,
           0px 8px 24px rgba(17, 17, 26, 0.05) inset,
           0px 16px 56px rgba(17, 17, 26, 0.05) inset`
        : `0 0 2px 1px color-mix(in oklch, black, transparent 85%) inset,
           0 0 10px 4px color-mix(in oklch, black, transparent 90%) inset,
           0px 4px 16px rgba(17, 17, 26, 0.05),
           0px 8px 24px rgba(17, 17, 26, 0.05),
           0px 16px 56px rgba(17, 17, 26, 0.05),
           0px 4px 16px rgba(17, 17, 26, 0.05) inset,
           0px 8px 24px rgba(17, 17, 26, 0.05) inset,
           0px 16px 56px rgba(17, 17, 26, 0.05) inset`
    }
  } else {
    if (isDarkMode.value) {
      if (!backdropFilterSupported) {
        return {
          ...baseStyles,
          background: 'rgba(0, 0, 0, 0.4)',
          border: '1px solid rgba(255, 255, 255, 0.2)',
          boxShadow: `inset 0 1px 0 0 rgba(255, 255, 255, 0.2),
                      inset 0 -1px 0 0 rgba(255, 255, 255, 0.1)`
        }
      }
      return {
        ...baseStyles,
        background: 'rgba(255, 255, 255, 0.1)',
        backdropFilter: 'blur(12px) saturate(1.8) brightness(1.2)',
        WebkitBackdropFilter: 'blur(12px) saturate(1.8) brightness(1.2)',
        border: '1px solid rgba(255, 255, 255, 0.2)',
        boxShadow: `inset 0 1px 0 0 rgba(255, 255, 255, 0.2),
                    inset 0 -1px 0 0 rgba(255, 255, 255, 0.1)`
      }
    }
    if (!backdropFilterSupported) {
      return {
        ...baseStyles,
        background: 'rgba(255, 255, 255, 0.4)',
        border: '1px solid rgba(255, 255, 255, 0.3)',
        boxShadow: `inset 0 1px 0 0 rgba(255, 255, 255, 0.5),
                    inset 0 -1px 0 0 rgba(255, 255, 255, 0.3)`
      }
    }
    return {
      ...baseStyles,
      background: 'rgba(255, 255, 255, 0.25)',
      backdropFilter: 'blur(12px) saturate(1.8) brightness(1.1)',
      WebkitBackdropFilter: 'blur(12px) saturate(1.8) brightness(1.1)',
      border: '1px solid rgba(255, 255, 255, 0.3)',
      boxShadow: `0 8px 32px 0 rgba(31, 38, 135, 0.2),
                  0 2px 16px 0 rgba(31, 38, 135, 0.1),
                  inset 0 1px 0 0 rgba(255, 255, 255, 0.4),
                  inset 0 -1px 0 0 rgba(255, 255, 255, 0.2)`
    }
  }
})

const glassSurfaceClasses =
  'relative flex items-center justify-center overflow-hidden transition-opacity duration-[260ms] ease-out'

const focusVisibleClasses = computed(() => {
  return isDarkMode.value
    ? 'focus-visible:outline-2 focus-visible:outline-[#0A84FF] focus-visible:outline-offset-2'
    : 'focus-visible:outline-2 focus-visible:outline-[#007AFF] focus-visible:outline-offset-2'
})

const updateFilterElements = () => {
  const elements = [
    { ref: redChannelRef, offset: props.redOffset },
    { ref: greenChannelRef, offset: props.greenOffset },
    { ref: blueChannelRef, offset: props.blueOffset }
  ]
  elements.forEach(({ ref: r, offset }) => {
    if (r.value) {
      r.value.setAttribute('scale', (props.distortionScale + offset).toString())
      r.value.setAttribute('xChannelSelector', props.xChannel)
      r.value.setAttribute('yChannelSelector', props.yChannel)
    }
  })
  if (gaussianBlurRef.value) {
    gaussianBlurRef.value.setAttribute('stdDeviation', props.displace.toString())
  }
}

const setupResizeObserver = () => {
  if (!containerRef.value || typeof ResizeObserver === 'undefined') return
  resizeObserver = new ResizeObserver(() => {
    setTimeout(updateDisplacementMap, 0)
  })
  resizeObserver.observe(containerRef.value)
}

watch(
  [
    () => props.width,
    () => props.height,
    () => props.borderRadius,
    () => props.borderWidth,
    () => props.brightness,
    () => props.opacity,
    () => props.blur,
    () => props.displace,
    () => props.distortionScale,
    () => props.redOffset,
    () => props.greenOffset,
    () => props.blueOffset,
    () => props.xChannel,
    () => props.yChannel,
    () => props.mixBlendMode
  ],
  () => {
    updateDisplacementMap()
    updateFilterElements()
  }
)

watch([() => props.width, () => props.height], () => {
  setTimeout(updateDisplacementMap, 0)
})

onMounted(() => {
  darkModeCleanup = updateDarkMode()
  nextTick(() => {
    updateDisplacementMap()
    updateFilterElements()
    setupResizeObserver()
  })
})

onBeforeUnmount(() => {
  if (darkModeCleanup) darkModeCleanup()
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
})
</script>

<style scoped>
.glass-surface-svg {
  width: 100%;
  height: 100%;
  pointer-events: none;
  position: absolute;
  inset: 0;
  opacity: 0;
  z-index: -10;
}

.glass-surface-content {
  width: 100%;
  height: 100%;
  display: block;
  padding: 0;
  border-radius: inherit;
  position: relative;
  z-index: 10;
}
</style>
