<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import Icon from '@/components/icons/Icon.vue'

/**
 * 轻量日期范围选择器(自建,不依赖第三方)
 * 返回 [startStr, endStr] 格式 YYYY-MM-DD
 * 使用 Teleport 渲染下拉面板到 body,避免被父级 stacking context 裁切
 */
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['update:modelValue'])

const showStart = ref(false)
const showEnd = ref(false)

const startBtnRef = ref(null)
const endBtnRef = ref(null)

const startDropdownStyle = ref({})
const endDropdownStyle = ref({})

const start = computed(() => props.modelValue?.[0] || '')
const end = computed(() => props.modelValue?.[1] || '')

function pad(n) { return String(n).padStart(2, '0') }
function toStr(d) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` }

function genMonthDays(year, month) {
  const first = new Date(year, month, 1)
  const last = new Date(year, month + 1, 0)
  const days = []
  const startWeekday = first.getDay()
  for (let i = 0; i < startWeekday; i++) days.push(null)
  for (let d = 1; d <= last.getDate(); d++) days.push(d)
  return days
}

const today = new Date()
const startView = ref({ year: today.getFullYear(), month: today.getMonth() })
const endView = ref({ year: today.getFullYear(), month: today.getMonth() })

const startDays = computed(() => genMonthDays(startView.value.year, startView.value.month))
const endDays = computed(() => genMonthDays(endView.value.year, endView.value.month))

const monthNames = ['一月','二月','三月','四月','五月','六月','七月','八月','九月','十月','十一月','十二月']

function shiftMonth(view, delta) {
  let m = view.month + delta
  let y = view.year
  if (m < 0) { m = 11; y-- }
  if (m > 11) { m = 0; y++ }
  view.year = y; view.month = m
}

function isSameDate(str, year, month, day) {
  if (!str) return false
  return str === `${year}-${pad(month + 1)}-${pad(day)}`
}

function computeStartPos() {
  if (!startBtnRef.value) return
  const r = startBtnRef.value.getBoundingClientRect()
  startDropdownStyle.value = {
    position: 'fixed',
    top: `${r.bottom + 8}px`,
    left: `${r.left}px`,
    zIndex: 9999
  }
}

function computeEndPos() {
  if (!endBtnRef.value) return
  const r = endBtnRef.value.getBoundingClientRect()
  endDropdownStyle.value = {
    position: 'fixed',
    top: `${r.bottom + 8}px`,
    left: `${r.left}px`,
    zIndex: 9999
  }
}

function openStart() {
  showStart.value = true
  showEnd.value = false
  nextTick(computeStartPos)
}

function openEnd() {
  showEnd.value = true
  showStart.value = false
  nextTick(computeEndPos)
}

function pickStart(day) {
  if (!day) return
  const d = new Date(startView.value.year, startView.value.month, day)
  emit('update:modelValue', [toStr(d), end.value])
  showStart.value = false
}
function pickEnd(day) {
  if (!day) return
  const d = new Date(endView.value.year, endView.value.month, day)
  emit('update:modelValue', [start.value, toStr(d)])
  showEnd.value = false
}

function onScrollOrResize() {
  if (showStart.value) computeStartPos()
  if (showEnd.value) computeEndPos()
}

function onDocClick(e) {
  if (showStart.value && startBtnRef.value && !startBtnRef.value.contains(e.target) && !e.target.closest('.date-dropdown-teleported')) {
    showStart.value = false
  }
  if (showEnd.value && endBtnRef.value && !endBtnRef.value.contains(e.target) && !e.target.closest('.date-dropdown-teleported')) {
    showEnd.value = false
  }
}

onMounted(() => {
  window.addEventListener('scroll', onScrollOrResize, true)
  window.addEventListener('resize', onScrollOrResize)
  document.addEventListener('click', onDocClick)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScrollOrResize, true)
  window.removeEventListener('resize', onScrollOrResize)
  document.removeEventListener('click', onDocClick)
})
</script>

<template>
  <div class="flex items-center gap-2">
    <div class="relative">
      <button
        ref="startBtnRef"
        class="glass-input flex items-center gap-2 cursor-pointer text-sm"
        :disabled="disabled"
        @click="openStart"
      >
        <Icon name="clock" :size="14" style="color: var(--text-tertiary)" />
        {{ start || '开始日期' }}
      </button>
      <Teleport to="body">
        <div v-if="showStart" class="glass-liquid date-dropdown-teleported" :style="startDropdownStyle" style="padding: 12px; width: 256px; border-radius: 12px;">
          <div class="flex items-center justify-between mb-3">
            <button @click="shiftMonth(startView, -1)" class="cursor-pointer p-1 rounded hover:bg-white/10"><Icon name="chevronRight" :size="14" style="transform: rotate(180deg)" /></button>
            <span class="text-sm font-medium">{{ startView.year }} {{ monthNames[startView.month] }}</span>
            <button @click="shiftMonth(startView, 1)" class="cursor-pointer p-1 rounded hover:bg-white/10"><Icon name="chevronRight" :size="14" /></button>
          </div>
          <div class="grid grid-cols-7 gap-1 text-center text-xs" style="color: var(--text-tertiary)">
            <span v-for="w in ['日','一','二','三','四','五','六']" :key="w" class="py-1">{{ w }}</span>
          </div>
          <div class="grid grid-cols-7 gap-1 text-center text-sm">
            <button
              v-for="(d, i) in startDays"
              :key="i"
              :disabled="!d"
              @click="pickStart(d)"
              class="py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-0"
              :style="isSameDate(start, startView.year, startView.month, d) ? { background: 'rgba(132, 204, 22, 0.18)', color: '#fff', boxShadow: 'inset 0 0 0 1px rgba(132, 204, 22, 0.30)' } : {}"
              :class="d && !isSameDate(start, startView.year, startView.month, d) && 'hover:bg-white/10'"
            >{{ d || '' }}</button>
          </div>
        </div>
      </Teleport>
    </div>
    <span style="color: var(--text-tertiary)">—</span>
    <div class="relative">
      <button
        ref="endBtnRef"
        class="glass-input flex items-center gap-2 cursor-pointer text-sm"
        :disabled="disabled"
        @click="openEnd"
      >
        <Icon name="clock" :size="14" style="color: var(--text-tertiary)" />
        {{ end || '结束日期' }}
      </button>
      <Teleport to="body">
        <div v-if="showEnd" class="glass-liquid date-dropdown-teleported" :style="endDropdownStyle" style="padding: 12px; width: 256px; border-radius: 12px;">
          <div class="flex items-center justify-between mb-3">
            <button @click="shiftMonth(endView, -1)" class="cursor-pointer p-1 rounded hover:bg-white/10"><Icon name="chevronRight" :size="14" style="transform: rotate(180deg)" /></button>
            <span class="text-sm font-medium">{{ endView.year }} {{ monthNames[endView.month] }}</span>
            <button @click="shiftMonth(endView, 1)" class="cursor-pointer p-1 rounded hover:bg-white/10"><Icon name="chevronRight" :size="14" /></button>
          </div>
          <div class="grid grid-cols-7 gap-1 text-center text-xs" style="color: var(--text-tertiary)">
            <span v-for="w in ['日','一','二','三','四','五','六']" :key="w" class="py-1">{{ w }}</span>
          </div>
          <div class="grid grid-cols-7 gap-1 text-center text-sm">
            <button
              v-for="(d, i) in endDays"
              :key="i"
              :disabled="!d"
              @click="pickEnd(d)"
              class="py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-0"
              :style="isSameDate(end, endView.year, endView.month, d) ? { background: 'rgba(132, 204, 22, 0.18)', color: '#fff', boxShadow: 'inset 0 0 0 1px rgba(132, 204, 22, 0.30)' } : {}"
              :class="d && !isSameDate(end, endView.year, endView.month, d) && 'hover:bg-white/10'"
            >{{ d || '' }}</button>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>
