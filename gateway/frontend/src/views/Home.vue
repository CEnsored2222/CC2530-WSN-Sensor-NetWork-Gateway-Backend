<script setup>
import { computed, onMounted, onBeforeUnmount, ref, shallowRef, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { getSocket } from '@/ws/socket'
import { realtime, overview } from '@/api/data'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassStat from '@/components/layout/GlassStat.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import ScrollReveal from '@/components/vuebits/ScrollReveal.vue'
import LineChart from '@/components/charts/LineChart.vue'
import Icon from '@/components/icons/Icon.vue'

const router = useRouter()

const loading = ref(true)
const overviewData = ref({ gateway_count: 0, device_count: 0, bound_device_count: 0, online_count: 0, alert_count: 0 })
const devices = ref([]) // [{ device, latest }]

const statRefs = ref({})

// 实时折线: 30 分钟滚动窗口, 双 Y 轴 (温湿左/光照右)
const WINDOW_MS = 30 * 60 * 1000
const chartSeries = shallowRef({ value: [] })
const rt = {} // key = `${deviceId}:${metric}` → [[ts_ms, value], ...]
const hiddenSeries = ref(new Set())
let raf = null

const METRIC_META = {
  temperature: { label: '温度', unit: '°C', color: '#f59e0b', icon: 'thermometer', yAxisIndex: 0, accent: 'amber' },
  humidity:    { label: '湿度', unit: '%',   color: '#14b8a6', icon: 'droplet',    yAxisIndex: 0, accent: 'teal' },
  light:       { label: '光照', unit: 'lux', color: '#a3e635', icon: 'sun',        yAxisIndex: 1, accent: 'sage' }
}

// 组合配色池:每个「设备×指标」组合分配独立颜色,最大化区分度
// 调色板围绕 v2 绿色极光色系(青绿/薄荷/酸橙/琥珀)展开,深/浅主题下均可读
const COMBO_COLORS = [
  '#84cc16', '#14b8a6', '#34d399', '#a3e635', '#fbbf24',
  '#10b981', '#22d3ee', '#a7f3d0', '#65a30d', '#0d9488',
  '#5eead4', '#bef264', '#facc15', '#06b6d4', '#15803d',
  '#4ade80', '#2dd4bf', '#d9f99d', '#fde68a', '#99f6e4'
]

// 组合颜色映射: key(`${devId}:${metric}`) -> color
const comboColorMap = ref({})
let comboCursor = 0
function comboColor(key) {
  if (!comboColorMap.value[key]) {
    comboColorMap.value[key] = COMBO_COLORS[comboCursor % COMBO_COLORS.length]
    comboCursor++
  }
  return comboColorMap.value[key]
}

function seriesKey(deviceId, metric) {
  return `${deviceId}:${metric}`
}
function seriesName(deviceName, metric) {
  return `${deviceName || '未知'} · ${METRIC_META[metric]?.label || metric}`
}
function isSeriesVisible(name) {
  return !hiddenSeries.value.has(name)
}

// 设备/LED 状态判定(兼容字符串与数字)
function isDeviceActive(s) { return s === 'active' || s === 1 || s === '1' }
function isLedOn(s) { return s === true || s === 1 || s === '1' || s === 'true' }

function parseDeviceType(t) {
  if (!t) return ['temperature', 'humidity', 'light']
  if (Array.isArray(t)) return t
  try {
    const arr = JSON.parse(t)
    return Array.isArray(arr) ? arr : ['temperature', 'humidity', 'light']
  } catch {
    return ['temperature', 'humidity', 'light']
  }
}

async function load() {
  loading.value = true
  try {
    const [ov, rtData] = await Promise.all([overview(), realtime()])
    overviewData.value = {
      gateway_count: ov.gateway_count ?? 0,
      device_count: ov.device_count ?? 0,
      bound_device_count: ov.bound_device_count ?? 0,
      online_count: ov.online_count ?? ov.bound_device_count ?? 0,
      alert_count: ov.alert_count ?? 0
    }
    const list = (rtData && rtData.devices) ? rtData.devices : (Array.isArray(rtData) ? rtData : [])
    devices.value = list.map((d) => ({
      device: d.device || d,
      latest: d.latest || d.latest_data || null,
      metrics: parseDeviceType((d.device || d).type)
    }))
    // 用 latest 预填 rt
    devices.value.forEach((d) => {
      if (!d.latest) return
      const ts = (d.latest.ts || d.latest.timestamp) * 1000
      d.metrics.forEach((m) => {
        if (d.latest[m] == null) return
        const key = `${d.device.id}:${m}`
        rt[key] = [[ts, d.latest[m]]]
      })
    })
    scheduleRebuild()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

function onSensorData(payload) {
  if (!payload || !payload.device_id) return
  const dev = devices.value.find((d) => d.device.id === payload.device_id)
  const ts = (payload.ts || payload.timestamp || Math.floor(Date.now() / 1000)) * 1000
  const metrics = dev ? dev.metrics : ['temperature', 'humidity', 'light']

  // 即时更新卡片 latest (不节流)
  if (dev) {
    dev.latest = {
      ts: ts / 1000,
      temperature: payload.temperature ?? dev.latest?.temperature,
      humidity: payload.humidity ?? dev.latest?.humidity,
      light: payload.light ?? dev.latest?.light,
      device_status: payload.device_status ?? dev.latest?.device_status,
      led_status: payload.led_status ?? dev.latest?.led_status
    }
  }

  // 推入 rt 并裁剪窗口
  metrics.forEach((m) => {
    if (payload[m] == null) return
    const key = `${payload.device_id}:${m}`
    if (!rt[key]) rt[key] = []
    const arr = rt[key]
    // 同毫秒去重
    if (arr.length && arr[arr.length - 1][0] === ts) {
      arr[arr.length - 1][1] = payload[m]
    } else {
      arr.push([ts, payload[m]])
    }
    // 裁剪窗口
    const cutoff = ts - WINDOW_MS
    while (arr.length && arr[0][0] < cutoff) arr.shift()
  })

  scheduleRebuild()
}

function onSubscriptionUpdated(payload) {
  // 关闭的指标清空对应 rt
  if (!payload || !Array.isArray(payload.enabled)) return
  const enabled = new Set(payload.enabled)
  Object.keys(rt).forEach((key) => {
    const [, metric] = key.split(':')
    if (!enabled.has(metric)) delete rt[key]
  })
  scheduleRebuild()
}

function scheduleRebuild() {
  if (raf) return
  raf = requestAnimationFrame(() => {
    raf = null
    rebuildSeries()
  })
}

function rebuildSeries() {
  const series = []
  const cutoff = Date.now() - WINDOW_MS
  devices.value.forEach((d) => {
    d.metrics.forEach((m) => {
      const key = `${d.device.id}:${m}`
      const arr = (rt[key] || []).filter((p) => p[0] >= cutoff)
      if (!arr.length) return
      const meta = METRIC_META[m]
      if (!meta) return
      const name = seriesName(d.device.name || d.device.mac || d.device.id, m)
      if (hiddenSeries.value.has(name)) return
      series.push({
        name,
        data: arr,
        color: comboColor(key),
        yAxisIndex: meta.yAxisIndex
      })
    })
  })
  chartSeries.value = { value: series }
}

function toggleSeries(name) {
  const s = new Set(hiddenSeries.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  hiddenSeries.value = s
  scheduleRebuild()
}

// 图例:两级结构
//   一级 = 设备(hover 展开二级)
//   二级 = 该设备下各指标(点击切换显隐)
// 一级点击 = 切换该设备下全部指标的显隐
const legendDevices = computed(() => {
  return devices.value.map((item) => {
    const devId = item.device.id
    const devName = item.device.name || item.device.mac || '未命名'
    const metrics = item.metrics || []
    const items = metrics.map((m) => {
      const key = seriesKey(devId, m)
      return {
        key,
        name: seriesName(devName, m),
        metric: m,
        metricLabel: METRIC_META[m]?.label || m,
        color: comboColor(key)
      }
    })
    const allHidden = items.length > 0 && items.every((it) => !isSeriesVisible(it.name))
    return { devId, devName, items, allHidden }
  })
})

function toggleDeviceAll(devItem) {
  const s = new Set(hiddenSeries.value)
  // 若有任一隐藏 → 全部显示;否则全部隐藏
  const anyHidden = devItem.items.some((it) => s.has(it.name))
  if (anyHidden) {
    devItem.items.forEach((it) => s.delete(it.name))
  } else {
    devItem.items.forEach((it) => s.add(it.name))
  }
  hiddenSeries.value = s
  scheduleRebuild()
}

function gotoDevices(id) {
  router.push({ name: 'devices', query: id ? { highlight: id } : {} })
}

const alertRevealText = '当传感器读数越限时,系统会按规则即时推送告警 — 严重程度分级,设备绑定精确到节点,记录可追溯。'

let socket
onMounted(() => {
  load()
  socket = getSocket()
  socket.off('sensor_data', onSensorData)
  socket.on('sensor_data', onSensorData)
  socket.off('subscription_updated', onSubscriptionUpdated)
  socket.on('subscription_updated', onSubscriptionUpdated)
})
onBeforeUnmount(() => {
  if (socket) {
    socket.off('sensor_data', onSensorData)
    socket.off('subscription_updated', onSubscriptionUpdated)
  }
  if (raf) cancelAnimationFrame(raf)
})

const onlineCount = computed(() => overviewData.value.online_count || 0)
</script>

<template>
  <div class="home page-container">
    <PageHeader
      title="实时监控"
      eyebrow="REALTIME"
      :rotating-words="['温度', '湿度', '光照', '状态']"
    />

    <!-- KPI 统计 -->
    <div class="stats-grid">
      <GlassStat
        :ref="el => { if (el) statRefs.gateway = el }"
        label="网关数量"
        :value="overviewData.gateway_count"
        unit="台"
        eyebrow="GATEWAYS"
        icon="gateway"
        accent="sage"
        :loaded="!loading"
      />
      <GlassStat
        :ref="el => { if (el) statRefs.device = el }"
        label="设备总数"
        :value="overviewData.device_count"
        unit="台"
        eyebrow="DEVICES"
        icon="devices"
        accent="teal"
        :loaded="!loading"
      />
      <GlassStat
        :ref="el => { if (el) statRefs.online = el }"
        label="在线设备"
        :value="onlineCount"
        unit="台"
        eyebrow="ONLINE"
        icon="wifi"
        accent="mint"
        :loaded="!loading"
      />
      <GlassStat
        :ref="el => { if (el) statRefs.alert = el }"
        label="告警总数"
        :value="overviewData.alert_count"
        unit="条"
        eyebrow="ALERTS"
        icon="bell"
        accent="amber"
        :loaded="!loading"
      />
    </div>

    <!-- 实时数据流图表 -->
      <div v-if="loading" class="chart-block">
        <GlassCard padding="p-6">
          <div class="chart-head">
            <div>
              <div class="glass-skeleton" style="width: 100px; height: 12px; margin-bottom: 8px" />
              <div class="glass-skeleton" style="width: 240px; height: 20px" />
            </div>
            <div class="glass-skeleton" style="width: 60px; height: 24px; border-radius: 999px" />
          </div>
          <div class="glass-skeleton" style="width: 100%; height: 340px; margin-top: 16px; border-radius: 8px" />
        </GlassCard>
      </div>
      <div v-else class="chart-block">
        <GlassCard padding="p-6">
          <div class="chart-head">
            <div>
              <p class="eyebrow mb-1">DATA STREAM</p>
              <h3 class="chart-title">实时数据流 · 30 分钟滚动窗口</h3>
            </div>
            <div class="chart-status">
              <span class="status-dot status-dot--connected" />
              <span class="chart-status-text">LIVE</span>
            </div>
          </div>

          <!-- 两级图例:一级设备(hover 展开二级指标),点击切换显隐 -->
          <div v-if="legendDevices.length" class="chart-legend" role="group" aria-label="切换数据系列">
            <div
              v-for="d in legendDevices"
              :key="d.devId"
              class="lg-dev"
              :class="{ off: d.allHidden }"
            >
              <button
                type="button"
                class="lg-dev-btn"
                data-cursor-target
                :title="d.allHidden ? '点击显示该设备全部' : '点击隐藏该设备全部'"
                @click="toggleDeviceAll(d)"
              >
                <span class="lg-dev-swatches">
                  <i
                    v-for="it in d.items"
                    :key="it.key"
                    :style="{ background: it.color }"
                    :class="{ dim: !isSeriesVisible(it.name) }"
                  ></i>
                </span>
                <span class="lg-dev-name">{{ d.devName }}</span>
                <span class="lg-dev-caret">▾</span>
              </button>
              <div class="lg-pop" role="group">
                <button
                  v-for="it in d.items"
                  :key="it.key"
                  type="button"
                  class="lg-metric"
                  :class="{ off: !isSeriesVisible(it.name) }"
                  data-cursor-target
                  :title="isSeriesVisible(it.name) ? '点击隐藏' : '点击显示'"
                  @click="toggleSeries(it.name)"
                >
                  <i :style="{ background: it.color }"></i>
                  <span class="lg-metric-name">{{ it.metricLabel }}</span>
                  <span class="lg-metric-state">{{ isSeriesVisible(it.name) ? '显示' : '隐藏' }}</span>
                </button>
              </div>
            </div>
          </div>

          <div v-if="chartSeries.value.length" class="chart-wrap">
            <LineChart :series="chartSeries.value" dual />
          </div>
          <div v-else class="chart-empty">
            <Icon name="activity" :size="40" class="opacity-30 mb-3" />
            <p class="text-sm" style="color: var(--text-tertiary)">等待传感器推送数据…</p>
          </div>
        </GlassCard>
      </div>

    <!-- 设备卡片网格 -->
      <div v-if="loading" class="devices-block">
        <div class="devices-head">
          <div class="glass-skeleton" style="width: 60px; height: 12px" />
          <div class="glass-skeleton" style="width: 160px; height: 20px; margin-top: 4px" />
        </div>
        <div class="devices-grid">
          <div v-for="i in 3" :key="i" class="glass-skeleton" style="height: 200px; border-radius: var(--radius-lg)" />
        </div>
      </div>
      <div v-else class="devices-block">
      <div class="devices-head">
        <p class="eyebrow">DEVICES</p>
        <h3 class="devices-title">设备实时状态</h3>
      </div>

      <div v-if="!devices.length && !loading" class="devices-empty-wrap">
        <GlassCard padding="p-8">
          <GlassEmpty
            icon="devices"
            title="暂无绑定设备"
            description="前往设备管理页绑定网关与终端设备"
          >
            <template #action>
              <button class="glass-btn glass-btn--primary" data-cursor-target @click="gotoDevices()">
                <Icon name="arrowRight" :size="14" /> 前往设备管理
              </button>
            </template>
          </GlassEmpty>
        </GlassCard>
      </div>

      <div v-else class="devices-grid">
        <GlassCard
          v-for="(d, i) in devices"
          :key="d.device.id"
          padding="p-5"
          class="device-card sheen-on-hover"
          :style="{ animationDelay: `${Math.min(i * 0.04, 0.2)}s` }"
          data-cursor-target
          @click="gotoDevices(d.device.id)"
        >
          <div class="device-card-head">
            <div class="device-name-row">
              <span class="status-dot" :class="d.latest?.device_status === 'sleep' ? 'status-dot--sleep' : 'status-dot--connected'" />
              <span class="device-name">{{ d.device.name || d.device.mac || '未命名' }}</span>
            </div>
            <span class="tag-pill">{{ d.metrics.length }} 指标</span>
          </div>
          <p class="device-mac">{{ d.device.mac || '—' }}</p>

          <div class="device-metrics">
            <div
              v-for="m in d.metrics"
              :key="m"
              class="device-metric"
              :style="{ color: METRIC_META[m]?.color }"
            >
              <Icon :name="METRIC_META[m]?.icon" :size="14" />
              <span class="device-metric-label">{{ METRIC_META[m]?.label }}</span>
              <span class="device-metric-value data-value">
                {{ d.latest && d.latest[m] != null ? Number(d.latest[m]).toFixed(m === 'light' ? 0 : 1) : '—' }}
              </span>
              <span class="device-metric-unit">{{ METRIC_META[m]?.unit }}</span>
            </div>

            <!-- LED 开关状态 -->
            <div class="device-metric device-led">
              <span class="device-metric-label">LED</span>
              <span class="led-pill" :class="{ on: isLedOn(d.latest?.led_status) }">
                <span class="led-bulb"></span>
                <span class="led-text">{{ isLedOn(d.latest?.led_status) ? '开' : '关' }}</span>
              </span>
            </div>
          </div>

          <!-- 休眠亚克力遮罩 -->
          <div v-if="!isDeviceActive(d.latest?.device_status)" class="sleep-veil" aria-hidden="true">
            <div class="veil-inner">
              <div class="veil-moon"><Icon name="moon" :size="30" style="color: var(--teal)" /></div>
              <div class="veil-text">休眠中</div>
              <div class="veil-sub eyebrow">设备已进入低功耗</div>
            </div>
          </div>
        </GlassCard>
      </div>
    </div>

    <!-- 告警说明 (ScrollReveal) -->
    <div class="alert-reveal-block">
      <GlassCard padding="p-4 px-6">
        <div class="alert-reveal-head">
          <Icon name="shield" :size="16" />
          <span class="eyebrow">ALERT SYSTEM</span>
        </div>
        <ScrollReveal
          :text="alertRevealText"
          tag="p"
          class="alert-reveal-text"
        />
      </GlassCard>
    </div>
  </div>
</template>

<style scoped>
.home { }

/* 骨架屏 → 内容的平滑切换 */
.fade-swap-enter-active,
.fade-swap-leave-active {
  transition: opacity 0.35s ease;
}
.fade-swap-enter-from,
.fade-swap-leave-to {
  opacity: 0;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1rem;
}
@media (max-width: 1024px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 480px) {
  .stats-grid { grid-template-columns: 1fr; }
}

.chart-block { margin-bottom: 1rem; }
.chart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 1rem;
}
.chart-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.chart-status {
  display: flex;
  align-items: center;
  gap: 6px;
}
.chart-status-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.12em;
  color: var(--mint);
}
.chart-wrap {
  height: 240px;
}
.chart-empty {
  height: 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

/* —— 两级图例:一级设备 hover 展开二级指标浮层 —— */
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
  max-width: 100%;
}
.lg-dev {
  position: relative;
}
.lg-dev-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  cursor: pointer;
  transition: color 0.2s ease, background 0.2s ease, border-color 0.2s ease;
  font-family: 'DM Sans', sans-serif;
}
.lg-dev-btn:hover {
  color: var(--text-primary);
  background: rgba(132, 204, 22, 0.10);
  border-color: rgba(132, 204, 22, 0.25);
}
.lg-dev-swatches {
  display: inline-flex;
  gap: 2px;
}
.lg-dev-swatches i {
  width: 8px;
  height: 9px;
  border-radius: 2px;
  transition: opacity 0.2s ease;
}
.lg-dev-swatches i.dim {
  opacity: 0.25;
}
.lg-dev-name {
  font-weight: 500;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.lg-dev-caret {
  font-size: 9px;
  color: var(--text-tertiary);
  transition: transform 0.2s ease;
}
.lg-dev:hover .lg-dev-caret,
.lg-dev:focus-within .lg-dev-caret {
  transform: rotate(180deg);
  color: var(--text-secondary);
}
.lg-dev.off .lg-dev-btn {
  color: var(--text-tertiary);
  opacity: 0.7;
}
.lg-dev.off .lg-dev-btn:hover {
  opacity: 1;
}

/* 二级浮层 */
.lg-pop {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 20;
  min-width: 172px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  background: var(--glass-bg);
  border: 1px solid rgba(132, 204, 22, 0.22);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32);
  opacity: 0;
  visibility: hidden;
  transform: translateY(-4px);
  transition: opacity 0.18s ease, transform 0.18s ease, visibility 0.18s;
}
.lg-dev:hover .lg-pop,
.lg-dev:focus-within .lg-pop {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}
.lg-metric {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  font-size: 12px;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  padding: 6px 8px;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s ease, color 0.15s ease;
  font-family: 'DM Sans', sans-serif;
}
.lg-metric:hover {
  background: rgba(132, 204, 22, 0.10);
  color: var(--text-primary);
}
.lg-metric i {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}
.lg-metric-name {
  flex: 1;
}
.lg-metric-state {
  font-size: 10px;
  color: var(--text-tertiary);
  letter-spacing: 0.04em;
}
.lg-metric.off {
  color: var(--text-tertiary);
}
.lg-metric.off i {
  background: transparent !important;
  border: 1px dashed var(--text-tertiary);
}
.lg-metric.off .lg-metric-state {
  color: var(--text-tertiary);
}

.devices-block { margin-bottom: 1rem; }
.devices-head {
  margin-bottom: 1rem;
}
.devices-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 18px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin-top: 4px;
}
.devices-grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1rem;
}

.device-card {
  cursor: pointer;
  height: 100%;
  animation: device-fade-in 0.5s ease both;
}
@keyframes device-fade-in {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
.device-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.device-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.device-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.device-mac {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 14px;
}
.device-metrics {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.device-metric {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.device-metric-label {
  color: var(--text-tertiary);
  flex: 1;
}
.device-metric-value {
  font-weight: 600;
}
.device-metric-unit {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* —— LED 状态药丸(绿色系) —— */
.device-led {
  margin-top: 2px;
}
.led-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-tertiary);
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--glass-border);
  background: rgba(255, 255, 255, 0.03);
  transition: color 0.3s ease, border-color 0.3s ease, background 0.3s ease;
}
.led-bulb {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: background 0.3s ease, box-shadow 0.3s ease;
  flex-shrink: 0;
}
.led-pill.on {
  color: var(--mint);
  border-color: rgba(52, 211, 153, 0.35);
  background: rgba(52, 211, 153, 0.08);
}
.led-pill.on .led-bulb {
  background: var(--mint);
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.18), 0 0 8px rgba(52, 211, 153, 0.55);
}

/* —— 休眠亚克力遮罩(绿色系) —— */
.device-card {
  position: relative;
}
.sleep-veil {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: grid;
  place-items: center;
  backdrop-filter: blur(16px) saturate(0.4);
  -webkit-backdrop-filter: blur(16px) saturate(0.4);
  background: rgba(10, 18, 14, 0.82);
  border-radius: var(--radius-lg);
  animation: veil-in 0.4s ease;
}
[data-theme="light"] .sleep-veil {
  background: rgba(230, 235, 230, 0.88);
}
@keyframes veil-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
.veil-inner {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px 18px;
  border-radius: var(--radius-md);
  background: var(--glass-bg);
  border: 1px solid rgba(52, 211, 153, 0.22);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.28);
}
.veil-moon {
  color: var(--teal);
  line-height: 1;
  filter: drop-shadow(0 0 8px rgba(20, 184, 166, 0.45));
  animation: moon-pulse 3s ease-in-out infinite;
}
@keyframes moon-pulse {
  0%, 100% { opacity: 0.85; transform: scale(1); }
  50%      { opacity: 1;    transform: scale(1.08); }
}
.veil-text {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 17px;
  color: var(--text-primary);
  letter-spacing: 0.02em;
}
.veil-sub {
  color: var(--text-tertiary);
}

.alert-reveal-block { margin-top: 1rem; }
.alert-reveal-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--mint);
  margin-bottom: 10px;
}
.alert-reveal-text {
  font-size: 15px;
  line-height: 1.7;
  color: var(--text-secondary);
  letter-spacing: 0.01em;
}
</style>
