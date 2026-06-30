<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'

const props = defineProps({
  columns: { type: Number, default: 26 },
  baseColor: { type: String, default: 'rgba(132, 204, 22, 0.10)' },
  glitchColor: { type: String, default: 'rgba(132, 204, 22, 0.32)' },
  accentColor: { type: String, default: 'rgba(20, 184, 166, 0.28)' },
  highlightColor: { type: String, default: 'rgba(163, 230, 53, 0.45)' },
  speed: { type: Number, default: 1 }
})

const canvas = ref(null)
let ctx = null
let animationId = null
let grid = []
let cellSize = 0
let cols = 0
let rows = 0
let lastTime = 0
const FRAME_INTERVAL = 1000 / 12 // ~12fps for subtle effect

const CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+=<>/\\|{}[]()'

function randomChar() {
  return CHARS[Math.floor(Math.random() * CHARS.length)]
}

function init() {
  const cv = canvas.value
  if (!cv) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const rect = cv.getBoundingClientRect()
  if (rect.width === 0 || rect.height === 0) return
  cv.width = rect.width * dpr
  cv.height = rect.height * dpr
  ctx = cv.getContext('2d')
  ctx.scale(dpr, dpr)

  cellSize = Math.max(10, Math.floor(rect.width / props.columns))
  cols = Math.ceil(rect.width / cellSize) + 1
  rows = Math.ceil(rect.height / cellSize) + 1

  ctx.font = `400 ${Math.floor(cellSize * 0.58)}px 'JetBrains Mono', monospace`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'

  grid = []
  for (let r = 0; r < rows; r++) {
    const row = []
    for (let c = 0; c < cols; c++) {
      row.push({
        char: randomChar(),
        glitchFrames: 0,
        color: props.baseColor
      })
    }
    grid.push(row)
  }
}

function draw(timestamp) {
  animationId = requestAnimationFrame(draw)
  if (!ctx || !canvas.value) return
  if (timestamp - lastTime < FRAME_INTERVAL) return
  lastTime = timestamp

  const rect = canvas.value.getBoundingClientRect()
  ctx.clearRect(0, 0, rect.width, rect.height)

  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cell = grid[r][c]

      if (Math.random() < 0.012 * props.speed) {
        cell.char = randomChar()
        cell.glitchFrames = 2 + Math.floor(Math.random() * 6)
        const rand = Math.random()
        if (rand < 0.55) cell.color = props.glitchColor
        else if (rand < 0.85) cell.color = props.accentColor
        else cell.color = props.highlightColor
      }

      if (cell.glitchFrames > 0) {
        cell.glitchFrames--
        if (cell.glitchFrames === 0) cell.color = props.baseColor
      }

      ctx.fillStyle = cell.color
      ctx.fillText(cell.char, c * cellSize + cellSize / 2, r * cellSize + cellSize / 2)
    }
  }
}

function onResize() {
  cancelAnimationFrame(animationId)
  init()
  lastTime = 0
  animationId = requestAnimationFrame(draw)
}

onMounted(() => {
  init()
  animationId = requestAnimationFrame(draw)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  cancelAnimationFrame(animationId)
  window.removeEventListener('resize', onResize)
})

watch(() => props.columns, onResize)
</script>

<template>
  <canvas ref="canvas" class="letter-glitch-canvas" />
</template>

<style scoped>
.letter-glitch-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
