<script setup>
import { ref, reactive, computed, shallowRef, onMounted, watch } from 'vue'
import { runPrediction, latestPrediction, predictionHistory, mlpStatus, mlpTrain, mlpFinetune, mlpEvaluate } from '@/api/prediction'
import { listGateways } from '@/api/gateway'
import { listDevices } from '@/api/device'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassSelect from '@/components/glass/GlassSelect.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import DecryptedText from '@/components/vuebits/DecryptedText.vue'
import ScrollReveal from '@/components/vuebits/ScrollReveal.vue'
import AnimatedContent from '@/components/vuebits/AnimatedContent.vue'
import LineChart from '@/components/charts/LineChart.vue'
import Icon from '@/components/icons/Icon.vue'

const ui = useUiStore()

const loading = ref(false)
const gateways = ref([])
const allDevices = ref([])
const currentPrediction = ref(null)
const mlpPredictions = ref({})   // { [metric]: prediction }
const history = ref([])
// 初始化标志:阻止 loadDevices 设置默认 device/metric 时触发 watcher 重复调用 loadLatest
const initialized = ref(false)

const chartSeries = shallowRef({ value: [] })

const METRIC_META = {
  temperature: { label: '温度', unit: '°C',  color: '#f59e0b' },
  humidity:    { label: '湿度', unit: '%',   color: '#14b8a6' },
  light:       { label: '光照', unit: 'lux', color: '#a3e635' }
}
const METRIC_LABELS_SHORT = { temperature: '温', humidity: '湿', light: '光' }

const HORIZONS = [60, 120, 180, 240]
const LOOKBACKS = [72, 144, 288, 432]

const MODEL_META = {
  linear:       { label: '线性回归',  group: 'classic', forMetrics: null },
  svr:          { label: 'SVR',       group: 'classic', forMetrics: null },
  knn:          { label: 'KNN',       group: 'classic', forMetrics: null },
  rf:           { label: '随机森林',  group: 'classic', forMetrics: null },
  mlp_temp_hum: { label: 'MLP·温湿',  group: 'mlp',     forMetrics: ['temperature', 'humidity'] },
  mlp_light:    { label: 'MLP·光照',  group: 'mlp',     forMetrics: ['light'] }
}

const form = reactive({
  device_id: null,
  metric: 'temperature',
  model_name: 'linear',
  horizon_minutes: 60,
  lookback: 144
})

const finetuneActive = ref(false)
const trainLoading = ref(false)
const evaluateLoading = ref(false)
const mlpStatusData = ref(null)

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

const currentDevice = computed(() => allDevices.value.find((d) => d.id === form.device_id) || null)

const metricOptions = computed(() => {
  const arr = currentDevice.value ? parseType(currentDevice.value.type) : ['temperature', 'humidity', 'light']
  return arr.map((m) => ({ value: m, label: `${METRIC_META[m]?.label || m} (${METRIC_META[m]?.unit || ''})` }))
})

const modelOptions = computed(() => {
  return Object.entries(MODEL_META)
    .filter(([k, m]) => !m.forMetrics || m.forMetrics.includes(form.metric))
    .map(([k, m]) => ({ value: k, label: m.label }))
})

const deviceOptions = computed(() =>
  allDevices.value.map((d) => ({
    value: d.id,
    label: `${d.name || d.mac || '设备#' + d.id} · ${d.gateway_name || '—'}`
  }))
)

const horizonOptions = HORIZONS.map((h) => ({ value: h, label: `${h} 分钟` }))
const lookbackOptions = LOOKBACKS.map((l) => ({ value: l, label: `${l} 步` }))

const isMlpModel = computed(() => form.model_name.startsWith('mlp_'))

// ============ forecastTable: predicted_values 对象 → 表格行(按时间步数值升序) ============
const forecastTable = computed(() => {
  if (!currentPrediction.value?.predicted_values) return []
  const metric = currentPrediction.value.metric || form.metric
  const meta = METRIC_META[metric]
  const unit = meta?.unit || ''
  return Object.entries(currentPrediction.value.predicted_values)
    .map(([k, v]) => ({ step: k, value: v, unit }))
    .sort((a, b) => parseInt(String(a.step).replace('t+', '')) - parseInt(String(b.step).replace('t+', '')))
})

// ============ buildSeries: 用 ` *` 后缀分割历史/预测 ============
function buildSeries(raw) {
  if (!raw || !Array.isArray(raw) || !raw.length) return []
  let splitIdx = raw.findIndex((p) => String(p.t || p[0] || '').endsWith(' *'))
  if (splitIdx < 0) {
    return [{
      name: METRIC_META[form.metric]?.label || '指标',
      color: METRIC_META[form.metric]?.color || '#84cc16',
      data: raw.map((p) => [String(p.t || p[0]).replace(' *', ''), p.v ?? p[1]])
    }]
  }
  const hist = raw.slice(0, splitIdx + 1).map((p) => [String(p.t || p[0]).replace(' *', ''), p.v ?? p[1]])
  const fut  = raw.slice(splitIdx).map((p) => [String(p.t || p[0]).replace(' *', ''), p.v ?? p[1]])
  return [
    { name: '历史', color: METRIC_META[form.metric]?.color || '#84cc16', data: hist },
    { name: '预测', color: '#a7f3d0', data: fut, dashStyle: 'Dash' }
  ]
}

// ============ snapshotToSeries: 后端 history_snapshot → buildSeries 输入 ============
function snapshotToSeries(pred) {
  if (!pred) return []
  const snap = pred.history_snapshot
  if (snap && Array.isArray(snap.times) && Array.isArray(snap.values)) {
    return snap.times.map((t, i) => ({ t, v: snap.values[i] }))
  }
  return []
}

// ============ pickMlpItem: MLP 返回数组时按 metric 取出对应条目 ============
function pickMlpItem(res, metric) {
  if (Array.isArray(res)) {
    return res.find((p) => p.metric === metric) || res[0] || null
  }
  return res
}

// ============ 加载 ============
async function loadDevices() {
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
      const arr = parseType(allDevices.value[0].type)
      if (!arr.includes(form.metric)) form.metric = arr[0] || 'temperature'
    }
  } catch (e) {}
}

async function loadHistory() {
  if (!form.device_id) return
  try {
    const res = await predictionHistory({ device_id: form.device_id, limit: 20 })
    history.value = Array.isArray(res) ? res : (res?.items || [])
  } catch (e) {}
}

async function loadLatest() {
  if (!form.device_id) return
  try {
    if (isMlpModel.value) {
      // MLP 多指标:取当前 metric 的缓存
      const cached = mlpPredictions.value[form.metric]
      if (cached) {
        currentPrediction.value = cached
        chartSeries.value = { value: buildSeries(snapshotToSeries(cached)) }
      }
    } else {
      const res = await latestPrediction({ device_id: form.device_id, metric: form.metric, model_name: form.model_name })
      currentPrediction.value = res
      chartSeries.value = { value: buildSeries(snapshotToSeries(res)) }
    }
  } catch (e) {}
}

async function loadMLPStatus() {
  if (!isMlpModel.value) { mlpStatusData.value = null; return }
  try {
    mlpStatusData.value = await mlpStatus({ model_type: form.model_name })
  } catch (e) {}
}

// ============ 执行预测 ============
async function predict() {
  if (!form.device_id) {
    ui.pushToast({ type: 'warning', title: '请选择设备' })
    return
  }
  loading.value = true
  try {
    const payload = {
      device_id: form.device_id,
      metric: form.metric,
      model_name: form.model_name,
      horizon_minutes: form.horizon_minutes,
      lookback: form.lookback
    }
    const res = await runPrediction(payload)
    const item = isMlpModel.value ? pickMlpItem(res, form.metric) : res
    currentPrediction.value = item
    chartSeries.value = { value: buildSeries(snapshotToSeries(item)) }
    if (isMlpModel.value && Array.isArray(res)) {
      // MLP 返回多指标数组,全部缓存
      const cache = { ...mlpPredictions.value }
      res.forEach((p) => {
        if (p && p.metric) cache[p.metric] = p
      })
      mlpPredictions.value = cache
    }
    ui.pushToast({ type: 'success', title: '预测完成' })
    await loadHistory()
  } catch (e) {} finally {
    loading.value = false
  }
}

// ============ MLP 管理 ============
async function trainMLP() {
  trainLoading.value = true
  try {
    await mlpTrain({ model_type: form.model_name })
    ui.pushToast({ type: 'success', title: 'MLP 预训练完成' })
    await loadMLPStatus()
  } catch (e) {} finally {
    trainLoading.value = false
  }
}

async function toggleFinetune() {
  finetuneActive.value = !finetuneActive.value
  if (finetuneActive.value) {
    try {
      await mlpFinetune({ model_type: form.model_name })
      ui.pushToast({ type: 'info', title: '微调已启动', message: '异步执行中,状态稍后更新' })
    } catch (e) {
      finetuneActive.value = false
    }
  }
}

async function evaluateMLP() {
  evaluateLoading.value = true
  try {
    await mlpEvaluate({ model_type: form.model_name })
    ui.pushToast({ type: 'success', title: '评估完成' })
    await loadMLPStatus()
  } catch (e) {} finally {
    evaluateLoading.value = false
  }
}

// ============ 切换 ============
watch(() => form.device_id, () => {
  if (!initialized.value || !currentDevice.value) return
  const arr = parseType(currentDevice.value.type)
  if (!arr.includes(form.metric)) form.metric = arr[0] || 'temperature'
  loadLatest()
  loadHistory()
})

watch(() => form.metric, () => {
  if (!initialized.value) return
  // 模型适配
  const m = MODEL_META[form.model_name]
  if (m?.forMetrics && !m.forMetrics.includes(form.metric)) {
    form.model_name = 'linear'
  }
  if (isMlpModel.value) loadMLPStatus()
  loadLatest()
})

watch(() => form.model_name, () => {
  if (!initialized.value) return
  if (isMlpModel.value) {
    loadMLPStatus()
    loadLatest()
  } else {
    mlpStatusData.value = null
    loadLatest()
  }
})

function selectHistory(item) {
  currentPrediction.value = item
  chartSeries.value = { value: buildSeries(snapshotToSeries(item)) }
}

function scoreText(p) {
  if (!p) return '—'
  const parts = []
  if (p.mae !== null && p.mae !== undefined) parts.push(`MAE ${Number(p.mae).toFixed(2)}`)
  if (p.r2 !== null && p.r2 !== undefined) parts.push(`R² ${Number(p.r2).toFixed(3)}`)
  return parts.length ? parts.join(' · ') : '—'
}

function fmtTime(s) {
  if (!s) return '—'
  return String(s).replace('T', ' ').slice(0, 19)
}

const revealText = '预测引擎融合经典回归与多层感知机 — 选择设备与模型,框定预测时域,即可在历史曲线上叠加未来轨迹。MLP 模型支持预训练、微调与评估,持续逼近真实走势。'

onMounted(async () => {
  await loadDevices()
  if (form.device_id) {
    await Promise.all([loadLatest(), loadHistory()])
    if (isMlpModel.value) loadMLPStatus()
  }
  // 初始化完成,此后 device/metric/model 的变更才由 watcher 驱动加载
  initialized.value = true
})
</script>

<template>
  <div class="prediction page-container">
    <PageHeader
      title="预测引擎"
      eyebrow="FORECAST"
      :rotating-words="['线性回归', 'SVR', 'KNN', '随机森林', 'MLP·温湿', 'MLP·光照']"
      subtitle="历史轨迹 · 未来预测"
    />

    <div class="pred-layout">
      <!-- 1. PREDICT 横向表单（全宽，GlassCard 包裹） -->
      <AnimatedContent :distance="40" direction="up" :duration="0.6">
        <GlassCard padding="p-5" :hover="false" class="predict-form-card">
          <div class="panel-head">
            <Icon name="sparkles" :size="14" />
            <span class="eyebrow">PREDICT</span>
          </div>

          <div class="panel-fields-h">
            <GlassSelect v-model="form.device_id" :options="deviceOptions" label="设备" placeholder="选择设备" />
            <GlassSelect v-model="form.metric" :options="metricOptions" label="指标" />
            <GlassSelect v-model="form.model_name" :options="modelOptions" label="模型" />
            <GlassSelect v-model="form.horizon_minutes" :options="horizonOptions" label="预测时域" />
            <GlassSelect v-model="form.lookback" :options="lookbackOptions" label="回看步数" />
            <div class="predict-action">
              <button
                class="glass-btn glass-btn--primary w-full"
                data-cursor-target
                :disabled="loading || !form.device_id"
                @click="predict"
              >
                <Icon v-if="loading" name="refresh" :size="14" class="spin" />
                <Icon v-else name="zap" :size="14" />
                <span>{{ loading ? '预测中…' : '执行预测' }}</span>
              </button>
            </div>
          </div>

          <div class="panel-reveal">
            <ScrollReveal :text="revealText" tag="p" class="reveal-text" />
          </div>
        </GlassCard>
      </AnimatedContent>

      <!-- 2. MLP 管理面板（过滤器正下方，全宽，仅 MLP 模型显示） -->
      <AnimatedContent v-if="isMlpModel" :distance="40" direction="up" :delay="0.05" :duration="0.6">
        <GlassCard padding="p-5" class="mlp-card">
          <div class="mlp-head">
            <div class="mlp-head-left">
              <Icon name="layers" :size="14" />
              <span class="eyebrow">MLP · {{ MODEL_META[form.model_name]?.label }}</span>
            </div>
            <div class="mlp-actions">
              <button
                class="glass-btn glass-btn--primary glass-btn-sm"
                data-cursor-target
                :disabled="trainLoading"
                @click="trainMLP"
              >
                <Icon v-if="trainLoading" name="refresh" :size="12" class="spin" />
                <Icon v-else name="play" :size="12" />
                <span>预训练</span>
              </button>
              <button
                class="glass-btn glass-btn-sm"
                :class="{ 'glass-btn--active': finetuneActive }"
                data-cursor-target
                @click="toggleFinetune"
              >
                <Icon name="refresh" :size="12" />
                <span>{{ finetuneActive ? '微调中…' : '微调' }}</span>
              </button>
              <button
                class="glass-btn glass-btn-sm"
                data-cursor-target
                :disabled="evaluateLoading"
                @click="evaluateMLP"
              >
                <Icon v-if="evaluateLoading" name="refresh" :size="12" class="spin" />
                <Icon v-else name="gauge" :size="12" />
                <span>评估</span>
              </button>
            </div>
          </div>

          <div v-if="!mlpStatusData" class="mlp-empty">
            <p class="text-xs" style="color: var(--text-tertiary)">尚未加载状态,点击预训练开始。</p>
          </div>

          <div v-else class="mlp-stats">
            <div class="mlp-stat">
              <span class="eyebrow">样本数</span>
              <span class="data-value">{{ mlpStatusData.num_samples_trained ?? '—' }}</span>
            </div>
            <div class="mlp-stat">
              <span class="eyebrow">训练损失</span>
              <span class="data-value">{{ mlpStatusData.train_loss != null ? Number(mlpStatusData.train_loss).toFixed(4) : '—' }}</span>
            </div>
            <div class="mlp-stat">
              <span class="eyebrow">验证损失</span>
              <span class="data-value">{{ mlpStatusData.val_loss != null ? Number(mlpStatusData.val_loss).toFixed(4) : '—' }}</span>
            </div>
            <div class="mlp-stat">
              <span class="eyebrow">上次训练</span>
              <span class="data-value">{{ fmtTime(mlpStatusData.last_train_time) }}</span>
            </div>
            <div class="mlp-stat">
              <span class="eyebrow">上次微调</span>
              <span class="data-value">{{ fmtTime(mlpStatusData.last_finetune_time) }}</span>
            </div>
          </div>
        </GlassCard>
      </AnimatedContent>

      <!-- 3. 评估参数带 stat-band（5 个独立小参数块横排，不合并到卡片） -->
      <AnimatedContent :distance="40" direction="up" :delay="0.1" :duration="0.6">
        <div class="stat-band">
          <template v-if="currentPrediction">
            <div class="stat-block">
              <span class="eyebrow">模型</span>
              <span class="data-value">{{ MODEL_META[currentPrediction.model_name || form.model_name]?.label || '模型' }}</span>
            </div>
            <div class="stat-block">
              <span class="eyebrow">预测时长</span>
              <span class="data-value">{{ currentPrediction.horizon_minutes || form.horizon_minutes }}<span class="stat-unit">min</span></span>
            </div>
            <div class="stat-block">
              <span class="eyebrow">预测点数</span>
              <span class="data-value">{{ Object.keys(currentPrediction.predicted_values || {}).length }}</span>
            </div>
            <div class="stat-block">
              <span class="eyebrow">评分</span>
              <DecryptedText :text="scoreText(currentPrediction)" class="stat-score" :speed="30" />
            </div>
            <div class="stat-block">
              <span class="eyebrow">生成时间</span>
              <span class="data-value">{{ fmtTime(currentPrediction.predicted_at) }}</span>
            </div>
          </template>
          <template v-else>
            <div v-for="i in 5" :key="i" class="stat-block stat-block--skeleton">
              <span class="eyebrow">—</span>
              <div class="glass-skeleton" style="height: 18px; width: 60%; border-radius: 4px" />
            </div>
          </template>
        </div>
      </AnimatedContent>

      <!-- 4. 预测曲线图（全宽） -->
      <AnimatedContent :distance="60" direction="up" :delay="0.1" class="chart-block">
        <GlassCard padding="p-6" class="chart-card">
          <div class="chart-head">
            <div class="min-w-0">
              <p class="eyebrow mb-1">TIMELINE</p>
              <h3 class="chart-title">
                {{ METRIC_META[form.metric]?.label || '指标' }} 预测曲线
                <span class="chart-title-sub">· {{ currentDevice?.name || '—' }}</span>
              </h3>
            </div>
            <div class="chart-legend">
              <span class="legend-item">
                <span class="legend-line solid" :style="{ background: METRIC_META[form.metric]?.color }" />
                历史
              </span>
              <span class="legend-item">
                <span class="legend-line dashed" />
                预测
              </span>
            </div>
          </div>

          <div v-if="!currentPrediction" class="chart-state">
            <GlassEmpty
              icon="chart"
              title="尚未预测"
              description="选择设备与模型,点击「执行预测」即可生成未来轨迹。"
              :decorative="false"
            />
          </div>
          <div v-else-if="loading" class="chart-state">
            <div class="glass-skeleton" style="height: 340px; border-radius: var(--radius-md)" />
          </div>
          <div v-else class="chart-wrap">
            <LineChart :series="chartSeries.value" :animate="true" />
          </div>
        </GlassCard>
      </AnimatedContent>

      <!-- 5. 双列区：左 预测数据点表格 · 右 预测历史记录（横向并排） -->
      <div class="two-col">
        <AnimatedContent :distance="40" direction="up" :delay="0.12">
          <GlassCard padding="p-5" class="forecast-card">
            <div class="forecast-head">
              <p class="eyebrow">FORECAST POINTS · {{ forecastTable.length }}</p>
              <h4 class="forecast-title">预测数据点</h4>
            </div>

            <div v-if="!forecastTable.length" class="forecast-empty">
              <p class="text-sm" style="color: var(--text-tertiary)">尚无预测数据点</p>
            </div>
            <div v-else class="forecast-table-wrap">
              <table class="forecast-table">
                <thead>
                  <tr>
                    <th>时间步</th>
                    <th>预测值</th>
                    <th>单位</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in forecastTable" :key="i">
                    <td class="mono">{{ row.step }}</td>
                    <td class="mono num">{{ row.value }}</td>
                    <td class="muted">{{ row.unit }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </GlassCard>
        </AnimatedContent>

        <AnimatedContent :distance="40" direction="up" :delay="0.15">
          <GlassCard padding="p-5" class="history-card">
            <div class="history-head">
              <p class="eyebrow">HISTORY · {{ history.length }}</p>
              <h4 class="history-title">历史预测记录</h4>
            </div>

            <div v-if="!history.length" class="history-empty">
              <p class="text-sm" style="color: var(--text-tertiary)">尚无历史预测记录</p>
            </div>

            <div v-else class="history-list">
              <div
                v-for="(item, i) in history.slice(0, 10)"
                :key="item.id || i"
                class="history-row"
                :class="{ active: currentPrediction && currentPrediction.id === item.id }"
                data-cursor-target
                @click="selectHistory(item)"
              >
                <div class="history-row-main">
                  <span class="history-model">{{ MODEL_META[item.model_name]?.label || item.model_name }}</span>
                  <span class="history-meta">{{ METRIC_LABELS_SHORT[item.metric] || item.metric }} · {{ item.horizon_minutes }}min</span>
                </div>
                <span class="history-score data-value">{{ scoreText(item) }}</span>
                <span class="history-time data-value">{{ fmtTime(item.predicted_at) }}</span>
              </div>
            </div>
          </GlassCard>
        </AnimatedContent>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prediction { }

/* ===== 单列纵向布局(参考原版,不再左右分栏) ===== */
.pred-layout {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
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
.panel-fields-h {
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 18px;
  align-items: flex-end;
}
.panel-fields-h > :deep(.glass-select-wrap),
.panel-fields-h > div {
  flex: 1 1 140px;
  min-width: 120px;
}
.predict-action {
  flex: 0 0 auto;
  min-width: 120px;
}
.predict-form-card { margin-bottom: 0; }
.panel-reveal {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px dashed var(--glass-border);
}
.reveal-text {
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-tertiary);
}

/* ===== MLP 管理面板(过滤器下方,全宽) ===== */
.mlp-card { position: relative; }
.mlp-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.5), rgba(20, 184, 166, 0.5), transparent);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}
.mlp-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--glass-border);
}
.mlp-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--mint);
}
.mlp-empty {
  padding: 12px 0;
  min-height: 62px;
  display: flex;
  align-items: center;
}
.mlp-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  min-height: 62px;
}
.mlp-stat {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}
.mlp-stat .data-value {
  font-size: 14px;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}
.mlp-actions {
  display: flex;
  flex-direction: row;
  gap: 10px;
  flex-wrap: wrap;
}
.glass-btn--active {
  background: rgba(52, 211, 153, 0.12) !important;
  border-color: rgba(52, 211, 153, 0.4) !important;
  color: var(--mint) !important;
}

/* ===== 评估参数带 stat-band(独立小参数块横排,不合并到卡片) ===== */
.stat-band {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}
.stat-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  min-height: 62px;
}
.stat-block--skeleton {
  justify-content: center;
}
.stat-block .data-value {
  font-size: 14px;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.stat-unit {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-left: 3px;
  font-weight: 400;
}
.stat-score {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--mint);
  letter-spacing: 0.04em;
}

/* ===== 图表卡 ===== */
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
.chart-legend {
  display: flex;
  gap: 16px;
  align-items: center;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}
.legend-line {
  display: inline-block;
  width: 18px;
  height: 2px;
  border-radius: 1px;
}
.legend-line.solid { background: var(--mint); }
.legend-line.dashed {
  background: repeating-linear-gradient(90deg, #a7f3d0 0 4px, transparent 4px 8px);
}

.chart-state {
  height: 340px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.chart-wrap {
  height: 340px;
}

/* ===== 双列区:预测数据点 + 历史记录(横向并排) ===== */
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
  align-items: stretch;
}

/* 两卡片统一样式:液态玻璃 + flex 列布局,内容区自适应填充保证等高 */
.forecast-card,
.history-card {
  position: relative;
  display: flex;
  flex-direction: column;
}
.forecast-card::before,
.history-card::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.5), rgba(20, 184, 166, 0.5), transparent);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}
.forecast-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}
.forecast-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 1rem;
}
.forecast-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
/* 表格滚动容器:固定高度对齐 t+60 行(6 行 + 表头),超出滚动 */
.forecast-table-wrap {
  flex: 0 0 280px;
  overflow-y: auto;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}
.forecast-table {
  width: 100%;
  border-collapse: collapse;
}
/* sticky 表头:固定在滚动容器顶部,透明背景与表格风格统一 */
.forecast-table thead {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--glass-light);
}
.forecast-table th,
.forecast-table td {
  text-align: left;
  padding: 10px 14px;
  font-size: 13px;
  border-bottom: 1px solid var(--glass-border);
}
.forecast-table th {
  font-weight: 500;
  color: var(--text-tertiary);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-family: 'DM Sans', sans-serif;
}
.forecast-table td.mono {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}
.forecast-table td.num {
  font-weight: 600;
  color: var(--text-primary);
}
.forecast-table td.muted {
  color: var(--text-tertiary);
}
/* 绿色系 hover 高亮(与历史记录 active 一致) */
.forecast-table tbody tr:hover {
  background: rgba(132, 204, 22, 0.06);
}
.forecast-table tr:last-child td {
  border-bottom: none;
}

/* ===== 历史列表 ===== */
.history-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 1rem;
}
.history-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.history-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}
.history-list {
  flex: 0 0 280px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}
.history-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}
.history-row:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--glass-border);
}
.history-row.active {
  background: rgba(132, 204, 22, 0.08);
  border-color: rgba(132, 204, 22, 0.3);
}
.history-row-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.history-model {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.history-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
}
.history-score {
  font-size: 11px;
  color: var(--mint);
  flex-shrink: 0;
}
.history-time {
  font-size: 11px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 缩小时:双列退化为单列,评估带退化为 2 列 */
@media (max-width: 1024px) {
  .two-col { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .stat-band { grid-template-columns: repeat(2, 1fr); }
}


</style>
