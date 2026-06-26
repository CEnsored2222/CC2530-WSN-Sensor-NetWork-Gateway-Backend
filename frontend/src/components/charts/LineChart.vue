<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  series: { type: Array, default: () => [] } // [{ name, data:[[t,v],...], color }]
})

const el = ref(null)
let chart = null

function readVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function themeColors() {
  return {
    surface:   readVar('--surface') || '#141b30',
    surfaceHi: readVar('--surface-hi') || '#1f2a44',
    ink:       readVar('--ink') || '#e9eef9',
    ink3:      readVar('--ink-3') || '#8993b1',
    ink4:      readVar('--ink-4') || '#5c6685',
    line:      readVar('--line') || '#232c46',
    paperDeep: readVar('--paper-deep') || '#060912'
  }
}

function baseOption() {
  const c = themeColors()
  return {
    grid: { top: 16, left: 8, right: 14, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.surfaceHi,
      borderColor: c.line,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: c.ink, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      axisPointer: { lineStyle: { color: c.ink4, type: 'dashed' } },
      formatter: (p) => {
        let s = `<div style="font-family:'IBM Plex Mono';font-size:10px;color:${c.ink4};letter-spacing:.06em">${p[0].axisValue}</div>`
        p.forEach((it) => {
          s += `<div style="margin-top:4px"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${it.color};margin-right:6px"></span>${it.seriesName} <b style="font-family:'IBM Plex Mono';color:${c.ink}">${it.value[1] ?? '—'}</b></div>`
        })
        return s
      }
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      axisLine: { lineStyle: { color: c.line } },
      axisTick: { show: false },
      axisLabel: { color: c.ink4, fontFamily: 'IBM Plex Mono', fontSize: 10, hideOverlap: true }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
      axisLabel: { color: c.ink4, fontFamily: 'IBM Plex Mono', fontSize: 10 }
    },
    series: []
  }
}

function render() {
  if (!chart) return
  const opt = baseOption()
  opt.series = props.series.map((s) => ({
    name: s.name,
    type: 'line',
    smooth: true,
    showSymbol: false,
    symbol: 'circle',
    symbolSize: 5,
    lineStyle: { width: 1.8, color: s.color },
    itemStyle: { color: s.color },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: s.color + '40' },
        { offset: 1, color: s.color + '00' }
      ])
    },
    data: s.data
  }))
  chart.setOption(opt, true)
}

function resize() { chart && chart.resize() }

function onThemeChange() { render() }

onMounted(() => {
  chart = echarts.init(el.value)
  render()
  window.addEventListener('resize', resize)
  window.addEventListener('theme-change', onThemeChange)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  window.removeEventListener('theme-change', onThemeChange)
  chart && chart.dispose()
  chart = null
})
watch(() => props.series, render, { deep: true })
</script>

<template>
  <div ref="el" class="chart"></div>
</template>

<style scoped>
.chart {
  width: 100%;
  height: 100%;
  min-height: 220px;
}
</style>
