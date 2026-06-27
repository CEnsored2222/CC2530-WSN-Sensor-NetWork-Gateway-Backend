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
  dual: { type: Boolean, default: false } // 是否启用双 Y 轴
})

const el = ref(null)
let chart = null
// 记录上一次渲染的 series name 集合,用于 detect 被移除的 series
let lastSeriesNames = new Set()

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

function buildYAxis(c) {
  if (!props.dual) {
    return {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: c.line, type: 'dashed' } },
      axisLabel: { color: c.ink4, fontFamily: 'IBM Plex Mono', fontSize: 10 }
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
      axisLabel: { color: c.ink4, fontFamily: 'IBM Plex Mono', fontSize: 10 } },
    { ...common, name: '光照', nameTextStyle: { color: c.ink4, fontSize: 9, padding: [0, -10, 0, 0] },
      axisLabel: { color: c.ink4, fontFamily: 'IBM Plex Mono', fontSize: 10 },
      splitLine: { show: false } }
  ]
}

function baseOption() {
  const c = themeColors()
  return {
    // 关闭动画:实时数据场景每次 setOption 不再播放从左到右入场动画,杜绝闪烁
    animation: false,
    // 过渡动画时长也置零,即使个别属性触发动画也瞬间完成
    animationDuration: 0,
    animationEasing: 'linear',
    grid: { top: 24, left: 8, right: props.dual ? 50 : 14, bottom: 8, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.surfaceHi,
      borderColor: c.line,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: c.ink, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      axisPointer: { lineStyle: { color: c.ink4, type: 'dashed' } },
      formatter: (p) => {
        // 时间轴:axisValue 是 timestamp number,格式化为 HH:mm:ss
        const t = new Date(p[0].axisValue)
        const ts = t.toLocaleTimeString('zh-CN', { hour12: false })
        let s = `<div style="font-family:'IBM Plex Mono';font-size:10px;color:${c.ink4};letter-spacing:.06em">${ts}</div>`
        p.forEach((it) => {
          s += `<div style="margin-top:4px"><span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${it.color};margin-right:6px"></span>${it.seriesName} <b style="font-family:'IBM Plex Mono';color:${c.ink}">${it.value[1] ?? '—'}</b></div>`
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
        fontFamily: 'IBM Plex Mono',
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
  const opt = baseOption()
  opt.series = props.series.map((s) => ({
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
    // 数据按时间戳排序(避免乱序导致线条回跳)
    data: (s.data || []).slice().sort((a, b) => a[0] - b[0])
  }))
  // 当前 series name 集合
  const curNames = new Set(opt.series.map((s) => s.name))
  // 移除已被删除的系列(ECharts merge 模式不会自动移除)
  for (const name of lastSeriesNames) {
    if (!curNames.has(name)) {
      chart.setOption({ series: [{ name, data: [] }] }, false)
    }
  }
  lastSeriesNames = curNames
  // 关键:普通 merge 模式(setOption 第二参数 false)
  // ECharts 会按 series.name 智能匹配新旧 series,只增量更新 data,不触发重绘
  // 已通过上面循环手动移除不存在的 series
  chart.setOption(opt, false)
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
watch(() => props.series, render, { deep: true })
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
