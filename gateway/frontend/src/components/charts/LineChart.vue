<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const props = defineProps({
  series: { type: Array, default: () => [] }, // [{ name, data:[[t,v],...], color, yAxisIndex? }]
  // yAxisIndex: 0=左轴(默认,温度/湿度等小数值),1=右轴(光照等大数值)
  dual: { type: Boolean, default: false }, // 是否启用双 Y 轴
  animate: { type: Boolean, default: false } // 首次渲染是否播放从左到右入场动画
})

const el = ref(null)
let chart = null
// 记录上一次渲染的 series name 集合,用于 detect 被移除的 series
let lastSeriesNames = new Set()
// 入场动画只播放一次,后续数据切换走 merge 模式避免 notMerge 全量重建的性能开销
let hasAnimated = false

function readVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function themeColors() {
  return {
    surface:   readVar('--bg-mid') || '#0f1a14',
    surfaceHi: readVar('--glass-bg') || 'rgba(255,255,255,0.04)',
    ink:       readVar('--text-primary') || 'rgba(255,255,255,0.95)',
    ink3:      readVar('--text-secondary') || 'rgba(255,255,255,0.62)',
    ink4:      readVar('--text-tertiary') || 'rgba(255,255,255,0.40)',
    line:      readVar('--glass-border') || 'rgba(132,204,22,0.12)',
    paperDeep: readVar('--bg-deep') || '#0a1410',
    accent:    readVar('--mint') || '#34d399',
    accent2:   readVar('--sage') || '#84cc16'
  }
}

function buildYAxis(c) {
  if (!props.dual) {
    return {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
      axisLabel: { color: c.ink4, fontFamily: 'JetBrains Mono', fontSize: 10 }
    }
  }
  // 双 Y 轴:左轴小数值(温/湿),右轴大数值(光照)
  const common = {
    type: 'value',
    scale: true,
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
  }
  return [
    { ...common, name: '温/湿', nameTextStyle: { color: c.ink4, fontSize: 9, padding: [0, 0, 0, -20] },
      axisLabel: { color: c.ink4, fontFamily: 'JetBrains Mono', fontSize: 10 } },
    { ...common, name: '光照', nameTextStyle: { color: c.ink4, fontSize: 9, padding: [0, -10, 0, 0] },
      axisLabel: { color: c.ink4, fontFamily: 'JetBrains Mono', fontSize: 10 },
      splitLine: { show: false } }
  ]
}

function baseOption() {
  const c = themeColors()
  // 仅首次渲染播放入场动画,后续切换走 merge 模式(无动画)避免 notMerge 全量重建
  const playAnim = props.animate && !hasAnimated
  return {
    animation: playAnim,
    animationDuration: playAnim ? 1200 : 0,
    animationDurationUpdate: 0,
    animationEasing: playAnim ? 'cubicInOut' : 'linear',
    grid: { top: 24, left: 8, right: props.dual ? 50 : 14, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 26, 20, 0.85)',
      borderColor: 'rgba(132, 204, 22, 0.20)',
      borderWidth: 1,
      padding: [10, 14],
      extraCssText: 'border-radius: 12px;',
      textStyle: { color: c.ink, fontFamily: 'DM Sans, sans-serif', fontSize: 12 },
      axisPointer: { lineStyle: { color: c.accent, type: 'dashed', width: 1 } },
      formatter: (p) => {
        const t = new Date(p[0].axisValue)
        const ts = t.toLocaleTimeString('zh-CN', { hour12: false })
        let s = `<div style="font-family:'JetBrains Mono';font-size:10px;color:${c.ink4};letter-spacing:.06em">${ts}</div>`
        p.forEach((it) => {
          s += `<div style="margin-top:4px"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${it.color};margin-right:6px"></span>${it.seriesName} <b style="font-family:'JetBrains Mono';color:${c.ink}">${it.value[1] ?? '—'}</b></div>`
        })
        return s
      }
    },
    xAxis: {
      type: 'time',
      boundaryGap: false,
      axisLine: { lineStyle: { color: c.line } },
      axisTick: { show: false },
      axisLabel: {
        color: c.ink4,
        fontFamily: 'JetBrains Mono',
        fontSize: 10,
        hideOverlap: true,
        formatter: (val) => {
          // val 是 timestamp,只显示 HH:mm
          const d = new Date(val)
          return d.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
        }
      }
    },
    yAxis: buildYAxis(c),
    series: []
  }
}

// 节流:用 requestAnimationFrame 合并同一帧内的多次 render 调用
// 避免高频 WS 推送每条都触发 setOption
let rafId = null
function scheduleRender() {
  if (rafId) return  // 已有挂起的渲染,跳过
  rafId = requestAnimationFrame(() => {
    rafId = null
    doRender()
  })
}

function doRender() {
  if (!chart) return
  const playAnim = props.animate && !hasAnimated
  const opt = baseOption()
  opt.series = props.series.map((s) => {
    const raw = s.data || []
    // 排序前先检查是否已有序,避免每次渲染都 O(n log n)
    let sorted = raw
    if (raw.length > 1) {
      let needSort = false
      for (let i = 1; i < raw.length; i++) {
        if (new Date(raw[i][0]) < new Date(raw[i - 1][0])) { needSort = true; break }
      }
      if (needSort) sorted = raw.slice().sort((a, b) => new Date(a[0]) - new Date(b[0]))
    }
    return {
      name: s.name,
      type: 'line',
      smooth: true,
      showSymbol: false,
      symbol: 'circle',
      symbolSize: 5,
      yAxisIndex: s.yAxisIndex || 0,
      lineStyle: { width: 1.8, color: s.color },
      itemStyle: { color: s.color },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: s.color + '40' },
          { offset: 1, color: s.color + '00' }
        ])
      },
      data: sorted
    }
  })
  const curNames = new Set(opt.series.map((s) => s.name))
  if (playAnim) {
    // 首次渲染:notMerge 全量替换,触发从左到右入场动画
    lastSeriesNames = curNames
    chart.setOption(opt, true)
    hasAnimated = true
  } else {
    // merge 模式:手动移除已删除的系列,增量更新 data,不触发重绘动画
    for (const name of lastSeriesNames) {
      if (!curNames.has(name)) {
        chart.setOption({ series: [{ name, data: [] }] }, false)
      }
    }
    lastSeriesNames = curNames
    chart.setOption(opt, false)
  }
}

// 对外仍叫 render,但内部走节流
function render() {
  scheduleRender()
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
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  window.removeEventListener('resize', resize)
  window.removeEventListener('theme-change', onThemeChange)
  chart && chart.dispose()
  chart = null
})
watch(() => props.series, render)
watch(() => props.dual, render)
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
