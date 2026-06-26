<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listGateways } from '@/api/gateway'
import { listDevices } from '@/api/device'
import { history } from '@/api/data'
import LineChart from '@/components/charts/LineChart.vue'

const loading = ref(false)
const gateways = ref([])
const allDevices = ref([]) // [{...dev, gateway_name}]

const form = reactive({
  device_id: null,
  metric: 'temperature',
  range: []
})

const records = ref([])
const queried = ref(false)

const METRICS = [
  { value: 'temperature', label: '温度', unit: '°C', color: '#f5a35c' },
  { value: 'humidity', label: '湿度', unit: '%', color: '#4dd6c1' },
  { value: 'light', label: '光照', unit: 'lx', color: '#b58cf0' }
]
const metricMeta = computed(() => METRICS.find((m) => m.value === form.metric))

// 设备 type 现在是 JSON 数组,如 ["temperature","humidity"]
// 直接从中提取指标列表
const METRIC_LABELS = {
  temperature: '温度', humidity: '湿度', light: '光照',
}
function devMetrics(dev) {
  const t = dev?.type
  if (Array.isArray(t) && t.length) return t
  return ['temperature', 'humidity', 'light']  // 无 type 时显示全部
}

// 当前选中设备可选的指标列表
const availableMetrics = computed(() => {
  const dev = allDevices.value.find((d) => d.id === form.device_id)
  const allow = dev ? devMetrics(dev) : ['temperature', 'humidity', 'light']
  return METRICS.filter((m) => allow.includes(m.value))
})

const chartSeries = computed(() => {
  if (!records.value.length) return []
  return [
    {
      name: `${metricMeta.value.label} (${metricMeta.value.unit})`,
      color: metricMeta.value.color,
      data: records.value.map((r) => [r.t, r.v])
    }
  ]
})

const stats = computed(() => {
  if (!records.value.length) return null
  const vals = records.value.map((r) => r.v).filter((v) => v !== null)
  if (!vals.length) return null
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const avg = vals.reduce((a, b) => a + b, 0) / vals.length
  return { min, max, avg, count: vals.length }
})

async function loadDevices() {
  const gws = await listGateways()
  gateways.value = gws
  const out = []
  for (const gw of gws) {
    const devs = await listDevices(gw.id).catch(() => [])
    devs.forEach((d) => out.push({ ...d, gateway_name: gw.name || gw.gw_uuid.slice(0, 8) }))
  }
  allDevices.value = out
  if (out.length && !form.device_id) form.device_id = out[0].id
}

async function query() {
  if (!form.device_id) return ElMessage.warning('请选择设备')
  loading.value = true
  queried.value = true
  try {
    const params = { device_id: form.device_id, metric: form.metric }
    if (form.range && form.range.length === 2) {
      params.start = form.range[0]
      params.end = form.range[1]
    }
    records.value = await history(params)
    if (!records.value.length) ElMessage.info('该范围内无数据')
  } catch (e) {
  } finally {
    loading.value = false
  }
}

// 切换设备时自动匹配指标并查询
function onDeviceChange() {
  const devMetrics2 = devMetrics(allDevices.value.find((d) => d.id === form.device_id))
  if (!devMetrics2.includes(form.metric)) {
    form.metric = devMetrics2[0] || 'temperature'
  }
  query()
}

function exportCsv() {
  if (!records.value.length) return
  const rows = [['time', form.metric], ...records.value.map((r) => [r.t, r.v])]
  const csv = rows.map((r) => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${form.metric}_${form.device_id}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  await loadDevices()
  if (form.device_id) query()
})
</script>

<template>
  <div class="history">
    <!-- 查询面板 -->
    <section class="panel rise rise-1">
      <div class="panel-head">
        <div>
          <div class="label-eyebrow">Query</div>
          <h2 class="panel-title display">历史曲线</h2>
        </div>
        <span class="panel-sub muted">按设备 · 指标 · 时间检索</span>
      </div>
      <div class="panel-form">
        <div class="f-item">
          <label class="label-eyebrow">设备</label>
          <el-select v-model="form.device_id" placeholder="选择设备" filterable @change="onDeviceChange">
            <el-option
              v-for="d in allDevices"
              :key="d.id"
              :label="(d.name || d.mac) + ' · ' + d.gateway_name"
              :value="d.id"
            />
          </el-select>
        </div>
        <div class="f-item">
          <label class="label-eyebrow">指标</label>
          <el-select v-model="form.metric" @change="query">
            <el-option v-for="m in availableMetrics" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </div>
        <div class="f-item grow">
          <label class="label-eyebrow">时间范围</label>
          <el-date-picker
            v-model="form.range"
            type="datetimerange"
            range-separator="—"
            start-placeholder="开始"
            end-placeholder="结束"
            format="YYYY-MM-DD HH:mm"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width:100%"
          />
        </div>
        <div class="f-item f-actions">
          <el-button type="primary" @click="query">查询</el-button>
          <el-button @click="exportCsv" :disabled="!records.length">导出 CSV</el-button>
        </div>
      </div>
    </section>

    <!-- 统计带 -->
    <section v-if="stats" class="stat-band rise rise-2">
      <div class="sb-card">
        <div class="label-eyebrow">最低</div>
        <div class="sb-val mono">{{ stats.min.toFixed(1) }}<span>{{ metricMeta.unit }}</span></div>
      </div>
      <div class="sb-card">
        <div class="label-eyebrow">最高</div>
        <div class="sb-val mono">{{ stats.max.toFixed(1) }}<span>{{ metricMeta.unit }}</span></div>
      </div>
      <div class="sb-card">
        <div class="label-eyebrow">平均</div>
        <div class="sb-val mono">{{ stats.avg.toFixed(1) }}<span>{{ metricMeta.unit }}</span></div>
      </div>
      <div class="sb-card">
        <div class="label-eyebrow">样本</div>
        <div class="sb-val mono">{{ stats.count }}<span>条</span></div>
      </div>
    </section>

    <!-- 图表 -->
    <section class="chart-card rise rise-3" v-loading="loading">
      <div class="chart-head">
        <div>
          <div class="label-eyebrow">Trend</div>
          <h3 class="chart-title display">
            {{ metricMeta?.label }} 趋势
            <span class="chart-unit muted">/ {{ metricMeta?.unit }}</span>
          </h3>
        </div>
        <span class="chart-color" :style="{ background: metricMeta?.color }"></span>
      </div>
      <div class="chart-box" v-if="records.length">
        <LineChart :series="chartSeries" />
      </div>
      <el-empty v-else-if="queried" description="无数据" :image-size="70" />
      <div v-else class="chart-ph muted">
        选择设备与指标后点击查询
      </div>
    </section>
  </div>
</template>

<style scoped>
.history { max-width: 1240px; }

.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 26px 28px;
  margin-bottom: 24px;
}
.panel-head {
  display: flex; justify-content: space-between; align-items: flex-end;
  padding-bottom: 20px; border-bottom: 1px solid var(--line); margin-bottom: 22px;
}
.panel-title { font-size: 24px; font-weight: 400; letter-spacing: -0.02em; margin-top: 4px; }
.panel-sub { font-size: 13px; }
.panel-form {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1.6fr auto;
  gap: 16px;
  align-items: end;
}
.f-item label { display: block; margin-bottom: 8px; }
.f-actions { display: flex; gap: 8px; }
@media (max-width: 980px) {
  .panel-form { grid-template-columns: 1fr 1fr; }
}

/* 统计 */
.stat-band {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}
.sb-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 18px 22px;
}
.sb-val {
  font-size: 32px;
  font-weight: 300;
  margin-top: 10px;
  letter-spacing: -0.02em;
}
.sb-val span {
  font-size: 13px;
  color: var(--ink-4);
  margin-left: 4px;
}
@media (max-width: 980px) {
  .stat-band { grid-template-columns: repeat(2, 1fr); }
}

/* 图表卡 */
.chart-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 26px 28px;
}
.chart-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px;
}
.chart-title { font-size: 22px; font-weight: 400; margin-top: 4px; }
.chart-unit { font-size: 14px; font-family: var(--font-mono); }
.chart-color { width: 28px; height: 3px; border-radius: 2px; }
.chart-box { height: 360px; }
.chart-ph { height: 360px; display: grid; place-items: center; font-size: 13px; }
</style>
