<script setup>
import { ref, reactive, computed, onMounted, watch, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { listGateways } from '@/api/gateway'
import { listDevices } from '@/api/device'
import { runPrediction, latestPrediction, predictionHistory } from '@/api/prediction'
import LineChart from '@/components/charts/LineChart.vue'

const loading = ref(false)
const gateways = ref([])
const allDevices = ref([])

const form = reactive({
  device_id: null,
  metric: 'temperature',
  model_name: 'linear',
  horizon_minutes: 60,
  lookback: 144,
})

const currentPrediction = ref(null)
const history = ref([])
const error = ref('')

const METRICS = [
  { value: 'temperature', label: '温度', unit: '°C', color: '#f5a35c' },
  { value: 'humidity', label: '湿度', unit: '%', color: '#4dd6c1' },
  { value: 'light', label: '光照', unit: 'lx', color: '#b58cf0' },
]
const MODELS = [
  { value: 'linear', label: 'LinearRegression', desc: '线性回归(基线)' },
  { value: 'svr', label: 'SVR', desc: '支持向量回归 · RBF' },
]
const HORIZONS = [30, 60, 120, 180, 240]  // 0.5h / 1h / 2h / 3h / 4h
const LOOKBACKS = [72, 144, 288, 432]     // 12h / 24h / 48h / 72h (按 10min/条)

const metricMeta = computed(() => METRICS.find((m) => m.value === form.metric))
const modelMeta = computed(() => MODELS.find((m) => m.value === form.model_name))

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

// 构建双线 series:历史(实线)+ 预测(虚线高亮)
const chartSeries = shallowRef({ value: [] })
function buildSeries(pred) {
  if (!pred || !pred.history_snapshot) return []
  const snap = pred.history_snapshot
  const times = snap.times || []
  const values = snap.values || []
  // 分割点:第一个带 ' *' 的预测点
  const splitIdx = times.findIndex((t) => typeof t === 'string' && t.endsWith(' *'))
  if (splitIdx < 0) {
    return [{
      name: `${metricMeta.value.label} (${metricMeta.value.unit})`,
      color: metricMeta.value.color,
      data: times.map((t, i) => [t.replace(' *', ''), values[i]]),
    }]
  }
  // 历史段 + 包含最后一个点用于衔接
  const histTimes = times.slice(0, splitIdx)
  const histVals = values.slice(0, splitIdx)
  const futTimes = times.slice(splitIdx).map((t) => t.replace(' *', ''))
  const futVals = values.slice(splitIdx)
  return [
    {
      name: `${metricMeta.value.label} 历史`,
      color: metricMeta.value.color,
      data: histTimes.map((t, i) => [t, histVals[i]]),
    },
    {
      name: `${metricMeta.value.label} 预测`,
      color: '#ff7a59',
      dashed: true,
      data: futTimes.map((t, i) => [t, futVals[i]]),
    },
  ]
}

// 预测数据点表格
const forecastTable = computed(() => {
  if (!currentPrediction.value?.predicted_values) return []
  return Object.entries(currentPrediction.value.predicted_values).map(([k, v]) => ({
    step: k,
    value: v,
    unit: metricMeta.value.unit,
  }))
})

// 评估指标说明
function scoreText(pred) {
  if (!pred) return ''
  const parts = []
  if (pred.mae != null) parts.push(`MAE ${pred.mae}`)
  if (pred.r2 != null) parts.push(`R² ${pred.r2}`)
  return parts.join(' · ')
}

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

async function loadLatestAndHistory() {
  if (!form.device_id) return
  try {
    const [latest, hist] = await Promise.all([
      latestPrediction({ device_id: form.device_id, metric: form.metric }),
      predictionHistory({ device_id: form.device_id, metric: form.metric, limit: 10 }),
    ])
    if (latest) {
      currentPrediction.value = latest
      chartSeries.value = { value: buildSeries(latest) }
    } else {
      currentPrediction.value = null
      chartSeries.value = { value: [] }
    }
    history.value = hist || []
  } catch (e) {
    // 忽略,首次进入无预测记录
  }
}

async function run() {
  if (!form.device_id) return ElMessage.warning('请选择设备')
  loading.value = true
  error.value = ''
  try {
    const pred = await runPrediction({
      device_id: form.device_id,
      metric: form.metric,
      model_name: form.model_name,
      horizon_minutes: form.horizon_minutes,
      lookback: form.lookback,
    })
    currentPrediction.value = pred
    chartSeries.value = { value: buildSeries(pred) }
    ElMessage.success(`预测完成 · ${pred.model_name} · ${Object.keys(pred.predicted_values).length} 个时间点`)
    // 刷新历史列表
    loadLatestAndHistory()
  } catch (e) {
    error.value = e?.response?.data?.error || e?.message || '预测失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

// 切换设备时自动匹配指标;切换指标时加载最新历史预测
watch(() => form.device_id, () => {
  const devMetrics2 = devMetrics(allDevices.value.find((d) => d.id === form.device_id))
  if (!devMetrics2.includes(form.metric)) {
    form.metric = devMetrics2[0] || 'temperature'
  }
  loadLatestAndHistory()
})
watch(() => form.metric, () => {
  loadLatestAndHistory()
})

onMounted(async () => {
  await loadDevices()
  if (form.device_id) loadLatestAndHistory()
})
</script>

<template>
  <div class="prediction">
    <!-- 控制面板 -->
    <section class="panel rise rise-1">
      <div class="panel-head">
        <div>
          <div class="label-eyebrow">Forecast Engine</div>
          <h2 class="panel-title display">智能预测</h2>
        </div>
        <span class="panel-sub muted">基于机器学习的时间序列趋势预测</span>
      </div>
      <div class="panel-form">
        <div class="f-item">
          <label class="label-eyebrow">设备</label>
          <el-select v-model="form.device_id" placeholder="选择设备" filterable>
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
          <el-select v-model="form.metric">
            <el-option v-for="m in availableMetrics" :key="m.value" :label="m.label + ' (' + m.unit + ')'" :value="m.value" />
          </el-select>
        </div>
        <div class="f-item">
          <label class="label-eyebrow">模型</label>
          <el-select v-model="form.model_name">
            <el-option v-for="m in MODELS" :key="m.value" :label="m.label + ' · ' + m.desc" :value="m.value" />
          </el-select>
        </div>
        <div class="f-item">
          <label class="label-eyebrow">预测时长</label>
          <el-select v-model="form.horizon_minutes">
            <el-option v-for="h in HORIZONS" :key="h" :label="h + ' min' + (h >= 60 ? ' (' + (h/60) + 'h)' : '')" :value="h" />
          </el-select>
        </div>
        <div class="f-item">
          <label class="label-eyebrow">历史样本</label>
          <el-select v-model="form.lookback">
            <el-option v-for="l in LOOKBACKS" :key="l" :label="l + ' 条 (' + (l*10/60) + 'h)'" :value="l" />
          </el-select>
        </div>
        <div class="f-item f-actions">
          <el-button type="primary" :loading="loading" @click="run">
            <span class="run-dot"></span>开始预测
          </el-button>
        </div>
      </div>
    </section>

    <!-- 评估带 -->
    <section v-if="currentPrediction" class="stat-band rise rise-2">
      <div class="sb-card">
        <div class="label-eyebrow">模型</div>
        <div class="sb-val mono">{{ modelMeta?.label }}</div>
      </div>
      <div class="sb-card">
        <div class="label-eyebrow">预测时长</div>
        <div class="sb-val mono">{{ currentPrediction.horizon_minutes }}<span>min</span></div>
      </div>
      <div class="sb-card">
        <div class="label-eyebrow">预测点数</div>
        <div class="sb-val mono">{{ Object.keys(currentPrediction.predicted_values || {}).length }}</div>
      </div>
      <div class="sb-card" :title="scoreText(currentPrediction)">
        <div class="label-eyebrow">评估</div>
        <div class="sb-val mono score" v-if="currentPrediction.mae != null">
          {{ scoreText(currentPrediction) }}
        </div>
        <div class="sb-val mono muted" v-else>—</div>
      </div>
      <div class="sb-card">
        <div class="label-eyebrow">预测时间</div>
        <div class="sb-val mono sm">{{ currentPrediction.predicted_at }}</div>
      </div>
    </section>

    <!-- 预测曲线 -->
    <section class="chart-card rise rise-3" v-loading="loading">
      <div class="chart-head">
        <div>
          <div class="label-eyebrow">Forecast</div>
          <h3 class="chart-title display">
            {{ metricMeta?.label }} 预测曲线
            <span class="chart-unit muted">/ {{ metricMeta?.unit }}</span>
          </h3>
        </div>
        <div class="legend">
          <span class="lg"><i :style="{ background: metricMeta?.color }"></i>历史</span>
          <span class="lg"><i class="dashed" :style="{ borderColor: '#ff7a59' }"></i>预测</span>
        </div>
      </div>
      <div class="chart-box" v-if="chartSeries.value && chartSeries.value.length">
        <LineChart :series="chartSeries.value" />
      </div>
      <el-empty v-else description="点击「开始预测」生成预测曲线" :image-size="70" />
    </section>

    <!-- 预测点表格 + 历史预测记录 -->
    <div class="two-col">
      <section v-if="forecastTable.length" class="forecast-table rise rise-4">
        <div class="card-head">
          <div>
            <div class="label-eyebrow">Forecast Points</div>
            <h3 class="chart-title display">预测数据点</h3>
          </div>
        </div>
        <table>
          <thead>
            <tr><th>时间步</th><th>预测值</th><th>单位</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in forecastTable" :key="i">
              <td class="mono">{{ row.step }}</td>
              <td class="mono num">{{ row.value }}</td>
              <td class="muted">{{ row.unit }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section v-if="history.length" class="history-card rise rise-4">
        <div class="card-head">
          <div>
            <div class="label-eyebrow">History</div>
            <h3 class="chart-title display">预测记录</h3>
          </div>
        </div>
        <div class="hist-list">
          <div
            v-for="h in history"
            :key="h.id"
            class="hist-row"
            :class="{ active: currentPrediction && h.id === currentPrediction.id }"
            @click="currentPrediction = h; chartSeries = { value: buildSeries(h) }"
          >
            <div class="hr-left">
              <div class="hr-model mono">{{ h.model_name }}</div>
              <div class="hr-time muted">{{ h.predicted_at }}</div>
            </div>
            <div class="hr-right">
              <div class="hr-points mono">{{ Object.keys(h.predicted_values || {}).length }} 点</div>
              <div class="hr-horizon muted">{{ h.horizon_minutes }}min</div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.prediction { max-width: 1240px; }

.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 26px 28px;
  margin-bottom: 24px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 22px;
}
.panel-title { font-size: 22px; font-weight: 500; }
.panel-sub { font-size: 12px; }
.panel-form {
  display: grid;
  grid-template-columns: repeat(5, 1fr) auto;
  gap: 14px;
  align-items: end;
}
.f-item { display: flex; flex-direction: column; gap: 6px; }
.f-item label { font-size: 10px; letter-spacing: 0.08em; }
.f-actions { display: flex; align-items: flex-end; }

.run-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #fff;
  margin-right: 6px;
  vertical-align: middle;
  box-shadow: 0 0 6px rgba(255,255,255,0.8);
}

/* 评估带 */
.stat-band {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}
.sb-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 16px 18px;
}
.sb-val {
  font-size: 18px;
  font-weight: 500;
  margin-top: 8px;
  color: var(--ink);
}
.sb-val span {
  font-size: 11px;
  color: var(--ink-4);
  margin-left: 4px;
  font-weight: 400;
}
.sb-val.score { font-size: 13px; color: var(--sage-deep); }
.sb-val.sm { font-size: 13px; }
.muted { color: var(--ink-4); }

/* 图表卡 */
.chart-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px 24px 12px;
  margin-bottom: 24px;
}
.chart-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.chart-title {
  font-size: 18px;
  font-weight: 500;
}
.chart-unit { font-size: 12px; margin-left: 6px; }
.legend {
  display: flex;
  gap: 14px;
}
.lg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ink-3);
}
.lg i {
  width: 12px;
  height: 2px;
  border-radius: 1px;
}
.lg i.dashed {
  height: 0;
  border-top: 2px dashed #ff7a59;
  background: transparent;
}
.chart-box {
  height: 320px;
}

/* 双列:预测点 + 历史 */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.forecast-table, .history-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
}
.card-head { margin-bottom: 14px; }

table {
  width: 100%;
  border-collapse: collapse;
}
table th, table td {
  text-align: left;
  padding: 10px 8px;
  font-size: 13px;
  border-bottom: 1px solid var(--line);
}
table th {
  font-weight: 500;
  color: var(--ink-3);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
table td.num {
  font-weight: 500;
  color: var(--ink);
}
table tr:last-child td { border-bottom: none; }

/* 历史列表 */
.hist-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow-y: auto;
}
.hist-row {
  display: flex;
  justify-content: space-between;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s var(--ease);
}
.hist-row:hover {
  border-color: var(--sage);
  background: var(--sage-tint);
}
.hist-row.active {
  border-color: var(--sage);
  background: var(--sage-tint);
}
.hr-left, .hr-right {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.hr-model {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink);
}
.hr-time { font-size: 11px; }
.hr-points { font-size: 13px; color: var(--sage-deep); }
.hr-horizon { font-size: 11px; text-align: right; }

@media (max-width: 1100px) {
  .panel-form { grid-template-columns: repeat(2, 1fr); }
  .stat-band { grid-template-columns: repeat(2, 1fr); }
  .two-col { grid-template-columns: 1fr; }
}
</style>
