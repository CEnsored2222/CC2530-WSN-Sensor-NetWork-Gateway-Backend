<script setup>
/**
 * 图标组件:通过 name prop 渲染对应 SVG 图标
 * 用法: <Icon name="home" /> 或 <Icon name="thermometer" :size="20" />
 * 所有图标为 24x24 viewBox, stroke-based (Lucide 风格)
 */
import { computed } from 'vue'
import { ICON_PATHS } from './paths.js'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
  strokeWidth: { type: [Number, String], default: 1.75 }
})

const paths = computed(() => ICON_PATHS[props.name] || ICON_PATHS.info)
</script>

<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="strokeWidth"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>
