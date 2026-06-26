<script setup>
import { computed, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { getSocket } from '@/ws/socket'
import { realtime, overview } from '@/api/data'
import LineChart from '@/components/charts/LineChart.vue'

const router = useRouter()

const loading = ref(true)
const overviewData = ref({ gateway_count: 0, device_count: 0, bound_device_count: 0 })
const devices = ref([]) // [{device, latest}]

// 实时折线:温度/湿度/光照(归一化多线)
const MAX_POINTS = 30
const chartSeries = shallowRef({ value: [] })
const rt = { temp: [], hum: [], light: [] }
const timeAxis = []

const METRIC_META = {
  temperature: { label: '温度', unit: '°C', color: '#f5a35c', field: 'temperature' },
  humidity: { label: '湿度', unit: '%', color: '#4dd6c1', field: 'humidity' },
  light: { label: '光照', unit: 'lx', color: '#b58cf0', field: 'light' }
}

// 图例可见性切换:key = series name
const SERIES_KEYS = [
  { key: '温度', name: '温度 °C', color: '#f5a35c' },
  { key: '湿度', name: '湿度 %', color: '#4dd6c1' },
  { key: '光照', name: '光照 lx', color: '#b58cf0' }
]
const hiddenSeries = ref(new Set()) // 存放被隐藏的 series name

function toggleSeries(name) {
  const s = new Set(hiddenSeries.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  hiddenSeries.value = s
}
function isSeriesVisible(name) {
  return !hiddenSeries.value.has(name)
}
// 过滤后的 series,传给 LineChart
const displaySeries = computed(() =>
  (chartSeries.value.value || []).filter((s) => isSeriesVisible(s.name))
)

async function load() {
  loading.value = true
  try {
    const [ov, rt2] = await Promise.all([overview(), realtime()])
    overviewData.value = ov
    devices.value = rt2.devices || []
  } finally {
    loading.value = false
  }
}

function fmt(v, d = 1) {
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(d)
}

// 设备是否处于活跃状态(同时兼容字符串 'active' 与数字 1)
function isDeviceActive(status) {
  return status === 'active' || status === 1 || status === '1'
}

const hasDevices = computed(() => devices.value.length > 0)

// WebSocket 实时数据
function onSocket() {
  const s = getSocket()
  s.on('sensor_data', (p) => {
    // p = { device_id, ...fields }
    const t = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    push(rt.temp, [t, p.temperature ?? null])
    push(rt.hum, [t, p.humidity ?? null])
    push(rt.light, [t, p.light ?? null])
    chartSeries.value = {
      value: [
        { name: '温度 °C', color: '#f5a35c', data: [...rt.temp] },
        { name: '湿度 %', color: '#4dd6c1', data: [...rt.hum] },
        { name: '光照 lx', color: '#b58cf0', data: [...rt.light] }
      ]
    }
    // 更新对应设备卡片的 latest
    const idx = devices.value.findIndex((d) => d.device.id === p.device_id)
    if (idx >= 0) {
      devices.value[idx].latest = { ...devices.value[idx].latest, ...p }
    }
  })
}

function push(arr, item) {
  arr.push(item)
  if (arr.length > MAX_POINTS) arr.shift()
}

onMounted(async () => {
  await load()
  onSocket()
})
</script>

<template>
  <div class="home">
    <!-- 顶部统计带 -->
    <section class="stat-band">
      <div class="stat-card rise rise-1">
        <div class="stat-label label-eyebrow">网关</div>
        <div class="stat-num display">{{ overviewData.gateway_count }}</div>
        <div class="stat-foot muted">已绑定</div>
      </div>
      <div class="stat-card rise rise-2">
        <div class="stat-label label-eyebrow">设备总数</div>
        <div class="stat-num display">{{ overviewData.device_count }}</div>
        <div class="stat-foot muted">个节点</div>
      </div>
      <div class="stat-card rise rise-3">
        <div class="stat-label label-eyebrow">已绑定</div>
        <div class="stat-num display">{{ overviewData.bound_device_count }}</div>
        <div class="stat-foot muted">监控中</div>
      </div>
      <div class="stat-card live rise rise-4">
        <div class="stat-label label-eyebrow">实时通道</div>
        <div class="stat-num display"><span class="live-dot dot-live"></span>WS</div>
        <div class="stat-foot muted">推送中</div>
      </div>
    </section>

    <!-- 实时折线 -->
    <section class="chart-card rise rise-3" v-if="hasDevices">
      <div class="card-head">
        <div>
          <div class="label-eyebrow">Realtime Stream</div>
          <h2 class="card-title display">实时数据流</h2>
        </div>
        <div class="legend" role="group" aria-label="切换数据系列">
          <button
            v-for="s in SERIES_KEYS"
            :key="s.key"
            type="button"
            class="lg"
            :class="{ off: !isSeriesVisible(s.name) }"
            :title="isSeriesVisible(s.name) ? '点击隐藏' : '点击显示'"
            @click="toggleSeries(s.name)"
          >
            <i :style="{ background: s.color }"></i>{{ s.key }}
          </button>
        </div>
      </div>
      <div class="chart-box">
        <LineChart :series="displaySeries" />
      </div>
    </section>

    <!-- 设备卡片 -->
    <section class="dev-section" v-if="hasDevices">
      <div class="section-head rise rise-4">
        <h2 class="section-title display">已监控设备</h2>
        <span class="section-sub muted">每个节点的最新读数</span>
      </div>
      <div class="dev-grid">
        <article
          v-for="(item, i) in devices"
          :key="item.device.id"
          class="dev-card rise"
          :class="{ sleeping: !isDeviceActive(item.latest?.device_status) }"
          :style="{ animationDelay: 0.3 + i * 0.06 + 's' }"
        >
          <div class="dc-content">
            <div class="dc-top">
              <div class="dc-name">{{ item.device.name || item.device.mac }}</div>
              <span class="dc-status" :class="item.latest?.device_status || 'sleep'">
                {{ item.latest?.device_status === 'active' ? '活跃' : '休眠' }}
              </span>
            </div>
            <div class="dc-mac mono">{{ item.device.mac }}</div>

            <div class="dc-reads">
              <div class="read">
                <div class="read-label label-eyebrow">温度</div>
                <div class="read-val mono"><b>{{ fmt(item.latest?.temperature) }}</b><span>°C</span></div>
              </div>
              <div class="read">
                <div class="read-label label-eyebrow">湿度</div>
                <div class="read-val mono"><b>{{ fmt(item.latest?.humidity) }}</b><span>%</span></div>
              </div>
              <div class="read">
                <div class="read-label label-eyebrow">光照</div>
                <div class="read-val mono"><b>{{ item.latest?.light ?? '—' }}</b><span>lx</span></div>
              </div>
              <div class="read">
                <div class="read-label label-eyebrow">LED</div>
                <div class="led-pill" :class="{ on: item.latest?.led_status }">
                  <span class="led-bulb"></span>{{ item.latest?.led_status ? '开' : '关' }}
                </div>
              </div>
            </div>
          </div>

          <!-- 休眠亚克力遮罩 -->
          <div v-if="!isDeviceActive(item.latest?.device_status)" class="sleep-veil" aria-hidden="true">
            <div class="veil-inner">
              <div class="veil-moon">☾</div>
              <div class="veil-text display">休眠中</div>
              <div class="veil-sub label-eyebrow">设备已进入低功耗</div>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- 空状态 -->
    <section class="empty" v-else-if="!loading">
      <div class="empty-art"></div>
      <h3 class="display">暂无监控数据</h3>
      <p class="muted">尚未绑定任何设备。前往设备管理,寻找并绑定网关下的设备,数据将在此实时呈现。</p>
      <el-button type="primary" @click="router.push({ name: 'devices' })">前往设备管理</el-button>
    </section>
  </div>
</template>

<style scoped>
.home {
  max-width: 1240px;
}

/* 统计带 */
.stat-band {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 18px;
  margin-bottom: 32px;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  position: relative;
  overflow: hidden;
}
.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 36px;
  height: 2px;
  background: var(--sage);
}
.stat-label {
  color: var(--ink-4);
  font-size: 10px;
}
.stat-num {
  font-size: 44px;
  font-weight: 300;
  line-height: 1;
  margin: 14px 0 6px;
  letter-spacing: -0.03em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-foot {
  font-size: 11px;
  color: var(--ink-4);
}
.live-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--sage);
  box-shadow: 0 0 0 4px var(--sage-soft);
}
.stat-card.live::before { background: var(--sage); }

/* 图表卡 */
.chart-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 26px 28px;
  margin-bottom: 36px;
}
.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 22px;
}
.card-title {
  font-size: 22px;
  font-weight: 400;
  margin-top: 4px;
}
.legend {
  display: flex;
  gap: 10px;
}
.lg {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--ink-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius);
  padding: 5px 10px;
  cursor: pointer;
  transition: all 0.2s var(--ease);
  font-family: var(--font-sans);
}
.lg:hover {
  color: var(--ink);
  background: var(--sage-tint);
  border-color: var(--line-strong);
}
.lg i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  transition: all 0.2s var(--ease);
}
.lg.off {
  color: var(--ink-5);
  opacity: 0.65;
}
.lg.off i {
  background: transparent !important;
  border: 1px dashed var(--ink-5);
}
.lg.off:hover {
  opacity: 1;
}
.chart-box {
  height: 280px;
}

/* 设备卡片网格 */
.section-head {
  display: flex;
  align-items: baseline;
  gap: 14px;
  margin-bottom: 18px;
}
.section-title {
  font-size: 22px;
  font-weight: 400;
}
.section-sub {
  font-size: 13px;
}
.dev-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 16px;
}
.dev-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px;
  transition: border-color 0.3s var(--ease), transform 0.3s var(--ease);
  position: relative;
  overflow: hidden;
}
.dev-card:hover {
  border-color: var(--sage);
  transform: translateY(-2px);
}

/* 休眠状态:卡片整体降饱和,边框转灰 */
.dev-card.sleeping {
  border-color: var(--line-strong);
}
.dev-card.sleeping:hover {
  border-color: var(--ink-5);
  transform: translateY(-1px);
}

/* 亚克力遮罩 */
.sleep-veil {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: grid;
  place-items: center;
  /* 模糊下方数据 + 亚克力质感 */
  backdrop-filter: blur(8px) saturate(0.6);
  -webkit-backdrop-filter: blur(8px) saturate(0.6);
  background: color-mix(in srgb, var(--paper) 32%, transparent);
  border-radius: var(--radius-lg);
  animation: veil-in 0.4s var(--ease);
}
@keyframes veil-in {
  from { opacity: 0; backdrop-filter: blur(0); }
  to   { opacity: 1; }
}
.veil-inner {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 14px;
  border-radius: var(--radius);
  background: color-mix(in srgb, var(--surface-hi) 70%, transparent);
  border: 1px solid var(--line-strong);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
}
.veil-moon {
  font-size: 30px;
  color: var(--amber);
  line-height: 1;
  filter: drop-shadow(0 0 8px var(--amber-soft));
  animation: moon-pulse 3s ease-in-out infinite;
}
@keyframes moon-pulse {
  0%, 100% { opacity: 0.85; transform: scale(1); }
  50%      { opacity: 1;    transform: scale(1.08); }
}
.veil-text {
  font-size: 17px;
  font-weight: 500;
  color: var(--ink);
  letter-spacing: 0.02em;
}
.veil-sub {
  color: var(--ink-4);
  font-size: 10px;
}
.dc-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.dc-name {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 500;
  letter-spacing: -0.01em;
}
.dc-status {
  font-size: 10px;
  padding: 3px 10px;
  border-radius: 999px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.dc-status.active {
  background: var(--sage-soft);
  color: var(--sage-deep);
}
.dc-status.sleep {
  background: var(--paper-deep);
  color: var(--ink-4);
}
.dc-mac {
  font-size: 11px;
  color: var(--ink-4);
  margin-top: 4px;
  margin-bottom: 18px;
  letter-spacing: 0.04em;
}
.dc-reads {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px 0;
}
.read-label {
  font-size: 9px;
  color: var(--ink-4);
}
.read-val {
  font-size: 13px;
  color: var(--ink-4);
  margin-top: 3px;
}
.read-val b {
  font-size: 22px;
  font-weight: 400;
  color: var(--ink);
  margin-right: 3px;
}
.led-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-3);
  margin-top: 6px;
}
.led-bulb {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--ink-5);
  transition: all 0.3s var(--ease);
}
.led-pill.on {
  color: var(--sage-deep);
}
.led-pill.on .led-bulb {
  background: var(--sage);
  box-shadow: 0 0 0 3px var(--sage-soft);
}

/* 空状态 */
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 80px 20px;
}
.empty-art {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  margin-bottom: 28px;
  background:
    radial-gradient(circle at 40% 35%, var(--sage-soft), transparent 60%),
    repeating-radial-gradient(circle at 50% 50%, transparent 0 8px, var(--line) 8px 9px);
  opacity: 0.7;
}
.empty h3 {
  font-size: 26px;
  font-weight: 400;
  margin-bottom: 10px;
}
.empty p {
  margin-bottom: 24px;
  max-width: 380px;
}

@media (max-width: 1100px) {
  .stat-band { grid-template-columns: repeat(2, 1fr); }
}
</style>
