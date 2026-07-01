<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { listGateways } from '@/api/gateway'
import { listDevices } from '@/api/device'
import { history } from '@/api/data'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassStat from '@/components/layout/GlassStat.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassSelect from '@/components/glass/GlassSelect.vue'
import GlassDatePicker from '@/components/glass/GlassDatePicker.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import AnimatedContent from '@/components/vuebits/AnimatedContent.vue'
import ScrollReveal from '@/components/vuebits/ScrollReveal.vue'
import LineChart from '@/components/charts/LineChart.vue'
import Icon from '@/components/icons/Icon.vue'

const ui = useUiStore()

const loading = ref(false)
const queried = ref(false)
const gateways = ref([])
const allDevices = ref([])         // [{ ...device, gateway_name }]
const records = ref([])            // [{ t, v }]
const chartReady = ref(false)

const METRIC_META = {
  temperature: { label: '温度',  unit: '°C',  color: '#f59e0b', icon: 'thermometer', accent: 'amber' },
  humidity:    { label: '湿度',  unit: '%',   color: '#14b8a6', icon: 'droplet',    accent: 'teal' },
  light:       { label: '光照',  unit: 'lux', color: '#a3e635', icon: 'sun',        accent: 'sage' }
}

const form = reactive({
  device_id: null,
  metric: 'temperature',
  range: []   // [startStr, endStr] YYYY-MM-DD
})

function parseType(t) {
  if (!t) return ['temperature', 'humidity', 'light']
  if (Array.isArray(t)) return t
  try {
    const arr = JSON.parse(t)
    return Array.isArray(arr) ? arr : ['temperature', 'humidity', 'light']
  } catch {
    return ['temperature', 'humidity', 'light']
  }
}

const deviceOptions = computed(() =>
  allDevices.value.map((d) => ({
    value: d.id,
    label: `${d.name || d.mac || '设备#' + d.id} · ${d.gateway_name || '—'}`
  }))
)

const currentDevice = computed(() => allDevices.value.find((d) => d.id === form.device_id) || null)

const metricOptions = computed(() => {
  const arr = currentDevice.value ? parseType(currentDevice.value.type) : ['temperature', 'humidity', 'light']
  return arr.map((m) => ({
    value: m,
    label: `${METRIC_META[m]?.label || m} (${METRIC_META[m]?.unit || ''})`
  }))
})

const stats = computed(() => {
  const vals = records.value.map((r) => r.v).filter((v) => v !== null && v !== undefined)
  if (!vals.length) return { min: null, max: null, avg: null, count: 0 }
  const sum = vals.reduce((a, b) => a + b, 0)
  return {
    min: Math.min(...vals),
    max: Math.max(...vals),
    avg: sum / vals.length,
    count: vals.length
  }
})

const chartSeries = computed(() => {
  if (!records.value.length) return []
  const meta = METRIC_META[form.metric] || METRIC_META.temperature
  return [{
    name: `${meta.label} (${meta.unit})`,
    color: meta.color,
    data: records.value.map((r) => [r.t, r.v])
  }]
})

// ============ 加载 ============
async function loadGatewaysAndDevices() {
  try {
    const gws = await listGateways()
    gateways.value = gws
    const list = await Promise.all(
      gws.map(async (gw) => {
        const devs = await listDevices(gw.id).catch(() => [])
        return (devs || []).map((d) => ({ ...d, gateway_name: gw.name || '未命名网关' }))
      })
    )
    allDevices.value = list.flat()
    if (allDevices.value.length && !form.device_id) {
      form.device_id = allDevices.value[0].id
      // 自动调整 metric
      const arr = parseType(allDevices.value[0].type)
      if (!arr.includes(form.metric)) form.metric = arr[0] || 'temperature'
    }
  } catch (e) { /* 拦截器 */ }
}

async function query() {
  if (!form.device_id) {
    ui.pushToast({ type: 'warning', title: '请先选择设备' })
    return
  }
  if (!form.metric) {
    ui.pushToast({ type: 'warning', title: '请选择指标' })
    return
  }
  loading.value = true
  chartReady.value = false
  try {
    const params = { device_id: form.device_id, metric: form.metric }
    if (form.range && form.range.length === 2) {
      if (form.range[0]) params.start = form.range[0] + ' 00:00:00'
      if (form.range[1]) params.end = form.range[1] + ' 23:59:59'
    }
    const res = await history(params)
    records.value = Array.isArray(res) ? res : (res?.records || [])
    queried.value = true
    if (!records.value.length) {
      ui.pushToast({ type: 'info', title: '查询结果为空', message: '该时间范围内无数据' })
    }
    // 触发图表渲染
    requestAnimationFrame(() => { chartReady.value = true })
  } catch (e) {
    records.value = []
  } finally {
    loading.value = false
  }
}

function exportCsv() {
  if (!records.value.length) return
  const meta = METRIC_META[form.metric] || METRIC_META.temperature
  const rows = [['time', meta.label]]
  records.value.forEach((r) => rows.push([r.t, r.v]))
  const csv = rows.map((row) => row.map((c) => `"${String(c ?? '').replace(/"/g, '""')}"`).join(',')).join('\n')
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${form.metric}_${form.device_id}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  ui.pushToast({ type: 'success', title: '已导出 CSV', message: `${records.value.length} 条数据` })
}

// 设备切换时自动调整 metric
watch(() => form.device_id, () => {
  if (!currentDevice.value) return
  const arr = parseType(currentDevice.value.type)
  if (!arr.includes(form.metric)) form.metric = arr[0] || 'temperature'
})

const revealText = '历史曲线承载传感器在时间维度上的真实轨迹 — 选择设备与指标,框定时间窗口,即可还原温度、湿度与光照的细微波动,辅以统计量与 CSV 导出,便于二次分析。'

onMounted(async () => {
  await loadGatewaysAndDevices()
  if (form.device_id) await query()
})
</script>

<template>
  <div class="history page-container">
    <PageHeader
      title="历史曲线"
      eyebrow="ARCHIVE"
      :rotating-words="['温度', '湿度', '光照', '趋势']"
    />

    <div class="history-layout">
      <!-- 左: 查询面板 -->
      <aside class="query-panel">
        <AnimatedContent :distance="40" direction="left" :duration="0.6">
          <GlassCard padding="p-5" :hover="false">
            <div class="panel-head">
              <Icon name="filter" :size="14" />
              <span class="eyebrow">QUERY</span>
            </div>

            <div class="panel-fields">
              <GlassSelect
                v-model="form.device_id"
                :options="deviceOptions"
                label="设备"
                placeholder="选择设备"
              />
              <GlassSelect
                v-model="form.metric"
                :options="metricOptions"
                label="指标"
                placeholder="选择指标"
              />
              <div>
                <label class="block mb-1.5 text-sm font-medium" style="color: var(--text-secondary)">时间范围</label>
                <GlassDatePicker v-model="form.range" />
              </div>
            </div>

            <div class="panel-actions">
              <button
                class="glass-btn glass-btn--primary w-full"
                data-cursor-target
                :disabled="loading || !form.device_id"
                @click="query"
              >
                <Icon v-if="loading" name="refresh" :size="14" class="spin" />
                <Icon v-else name="search" :size="14" />
                <span>{{ loading ? '查询中…' : '查询' }}</span>
              </button>
              <button
                class="glass-btn w-full"
                data-cursor-target
                :disabled="!records.length"
                @click="exportCsv"
              >
                <Icon name="download" :size="14" />
                <span>导出 CSV</span>
              </button>
            </div>

            <div class="panel-reveal">
              <ScrollReveal :text="revealText" tag="p" class="reveal-text" />
            </div>
          </GlassCard>
        </AnimatedContent>
      </aside>

      <!-- 右: 图表 + 统计 -->
      <section class="main-panel">
        <!-- 统计行 -->
        <AnimatedContent :distance="40" direction="up" :duration="0.6">
          <div class="stats-grid">
            <GlassStat
              label="数据点"
              :value="stats.count"
              unit="条"
              eyebrow="COUNT"
              icon="activity"
              accent="sage"
            />
            <GlassStat
              label="平均值"
              :value="stats.avg ?? 0"
              :decimals="2"
              :unit="METRIC_META[form.metric]?.unit || ''"
              eyebrow="AVG"
              icon="gauge"
              accent="teal"
            />
            <GlassStat
              label="最高值"
              :value="stats.max ?? 0"
              :decimals="2"
              :unit="METRIC_META[form.metric]?.unit || ''"
              eyebrow="MAX"
              icon="trendUp"
              accent="amber"
            />
            <GlassStat
              label="最低值"
              :value="stats.min ?? 0"
              :decimals="2"
              :unit="METRIC_META[form.metric]?.unit || ''"
              eyebrow="MIN"
              icon="trendDown"
              accent="mint"
            />
          </div>
        </AnimatedContent>

        <!-- 图表 -->
        <AnimatedContent :distance="60" direction="up" :delay="0.1" class="chart-block">
          <GlassCard padding="p-6" class="chart-card">
            <div class="chart-head">
              <div class="min-w-0">
                <p class="eyebrow mb-1">TIMELINE</p>
                <h3 class="chart-title">
                  {{ METRIC_META[form.metric]?.label || '指标' }} 趋势曲线
                  <span class="chart-title-sub">· {{ currentDevice?.name || currentDevice?.mac || '—' }}</span>
                </h3>
              </div>
              <div class="chart-meta">
                <span class="metric-pill" :style="{ color: METRIC_META[form.metric]?.color, borderColor: METRIC_META[form.metric]?.color + '40' }">
                  <span class="metric-dot" :style="{ background: METRIC_META[form.metric]?.color }" />
                  {{ METRIC_META[form.metric]?.unit }}
                </span>
              </div>
            </div>

            <!-- 状态: 未查询 -->
            <div v-if="!queried && !loading" class="chart-state">
              <GlassEmpty
                icon="chart"
                title="尚未查询"
                description="选择设备、指标与时间范围,点击查询即可绘制曲线。"
                :decorative="false"
              />
            </div>

            <!-- 状态: 加载中 -->
            <div v-else-if="loading" class="chart-state">
              <div class="glass-skeleton" style="height: 340px; border-radius: var(--radius-md)" />
            </div>

            <!-- 状态: 空结果 -->
            <div v-else-if="!records.length" class="chart-state">
              <GlassEmpty
                icon="activity"
                title="无数据"
                description="该时间范围内未找到记录,请尝试调整时间范围或设备。"
                :decorative="false"
              />
            </div>

            <!-- 图表 -->
            <div v-else class="chart-wrap">
              <LineChart :series="chartSeries" :animate="true" />
            </div>
          </GlassCard>
        </AnimatedContent>
      </section>
    </div>
  </div>
</template>

<style scoped>
.history { }

.history-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 1.5rem;
  align-items: stretch;
}
@media (max-width: 1024px) {
  .history-layout {
    grid-template-columns: 1fr;
  }
}

/* ===== 查询面板 ===== */
.query-panel {
  display: flex;
  flex-direction: column;
}
.query-panel > * {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.query-panel :deep(.glass-card) {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--mint);
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--glass-border);
}
.panel-fields {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 18px;
}
.panel-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}
.panel-reveal {
  padding-top: 16px;
  border-top: 1px dashed var(--glass-border);
}
.reveal-text {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-tertiary);
  letter-spacing: 0.01em;
}

/* ===== 主面板 ===== */
.main-panel {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
}
@media (max-width: 1280px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 480px) {
  .stats-grid { grid-template-columns: 1fr; }
}

.chart-card { position: relative; }
.chart-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 1rem;
}
.chart-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 18px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.chart-title-sub {
  font-size: 13px;
  color: var(--text-tertiary);
  font-weight: 400;
  font-family: 'DM Sans', sans-serif;
  margin-left: 4px;
}
.chart-meta {
  flex-shrink: 0;
}
.metric-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  letter-spacing: 0.08em;
  border: 1px solid;
  background: rgba(255, 255, 255, 0.03);
}
.metric-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.chart-state {
  height: 340px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chart-wrap {
  position: relative;
  height: 340px;
}

.spin {
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }


</style>
