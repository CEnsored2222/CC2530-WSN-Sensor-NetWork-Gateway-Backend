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

function buildSeriesOption(s) {
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
    // 数据点按时间戳排序,避免乱序导致线条回跳
    data: (s.data || []).slice().sort((a, b) => a[0] - b[0])
  }
}

// 已渲染 series 的 name → 索引映射,用于增量更新
let renderedNames = new Set()

function render() {
  if (!chart) return
  const incoming = props.series || []
  const incomingNames = new Set(incoming.map((s) => s.name))

  // 1) 移除已不存在的 series(通过 name 比对)
  const toRemove = [...renderedNames].filter((n) => !incomingNames.has(n))
  if (toRemove.length) {
    chart.setOption({
      series: toRemove.map((n) => ({ name: n, data: [] }))
    }, false)
  }

  // 2) 增量更新:对每个 series 只设置 data,不重建样式配置
  //    ECharts 会按 name 匹配并复用已有 series 实例,只刷新 data
  const seriesOpt = incoming.map((s) => {
    // 已存在的 series → 只提供 data(避免重建 lineStyle/areaStyle 触发重绘)
    if (renderedNames.has(s.name)) {
      return {
        name: s.name,
        data: (s.data || []).slice().sort((a, b) => a[0] - b[0])
      }
    }
    // 新 series → 完整配置
    return buildSeriesOption(s)
  })

  // notMerge=false + lazyUpdate=true:延迟到下一帧合并更新,避免连续 setOption 抖动
  chart.setOption({ series: seriesOpt }, { notMerge: false, lazyUpdate: true })

  // 3) 同步基础配置(坐标轴等,仅在首次或主题变更时执行)
  if (renderedNames.size === 0 || toRemove.length > 0) {
    const base = baseOption()
    // 不覆盖 series(已增量更新),仅同步 axis/tooltip/grid
    delete base.series
    chart.setOption(base, false)
  }

  renderedNames = incomingNames
}

function resize() { chart && chart.resize() }

function onThemeChange() {
  // 主题变更:重置缓存,强制下次 render 重新下发完整配置
  renderedNames = new Set()
  if (chart) chart.clear()
  render()
}

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
  renderedNames = new Set()
})
watch(() => props.series, render, { deep: true })
watch(() => props.dual, () => {
  // dual 切换:Y 轴结构变化,需重置缓存以重建坐标系
  renderedNames = new Set()
  if (chart) chart.clear()
  render()
})
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
