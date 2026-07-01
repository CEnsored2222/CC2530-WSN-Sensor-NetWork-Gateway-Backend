<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { listRules, createRule, updateRule, deleteRule, toggleRule, listRecords, alertStats } from '@/api/alert'
import { listGateways } from '@/api/gateway'
import { listDevices } from '@/api/device'
import { getSocket } from '@/ws/socket'
import { useUiStore } from '@/stores/ui'
import { useUserStore } from '@/stores/user'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassStat from '@/components/layout/GlassStat.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassTabs from '@/components/glass/GlassTabs.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassInput from '@/components/glass/GlassInput.vue'
import GlassSelect from '@/components/glass/GlassSelect.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import FadeContent from '@/components/vuebits/FadeContent.vue'
import GradualBlur from '@/components/vuebits/GradualBlur.vue'
import Icon from '@/components/icons/Icon.vue'

const ui = useUiStore()
const user = useUserStore()

const tab = ref(0)  // 0=records 1=rules

const stats = ref({ counts: { info: 0, warning: 0, critical: 0 }, total: 0, recent: [] })
const statsLoaded = ref(false)
const rules = ref([])
const records = ref([])
const recTotal = ref(0)
const recForm = reactive({ page: 1, size: 20, severity: '' })
const liveAlerts = ref([])   // 队列上限 6
const loading = ref(false)

const gatewayTree = ref([])  // [{ ...gw, devices: [] }]

const METRIC_LABELS = { temperature: '温度', humidity: '湿度', light: '光照' }
const OP_LABELS = { gt: '>', lt: '<', gte: '≥', lte: '≤', eq: '=' }
const SEVERITY_META = {
  info:     { label: '信息', color: '#14b8a6', bg: 'rgba(20,184,166,0.12)' },
  warning:  { label: '警告', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  critical: { label: '严重', color: '#f87171', bg: 'rgba(248,113,113,0.12)' }
}

const OPERATOR_OPTS = [
  { value: 'gt', label: '> 大于' },
  { value: 'lt', label: '< 小于' },
  { value: 'gte', label: '≥ 大于等于' },
  { value: 'lte', label: '≤ 小于等于' },
  { value: 'eq', label: '= 等于' }
]
const METRIC_OPTS = [
  { value: 'temperature', label: '温度 (°C)' },
  { value: 'humidity', label: '湿度 (%)' },
  { value: 'light', label: '光照 (lux)' }
]
const LOGIC_OPTS = [
  { value: 'none', label: '单条件' },
  { value: 'and', label: 'AND 同时满足' },
  { value: 'or', label: 'OR 任一满足' }
]
const SEVERITY_OPTS = [
  { value: 'info', label: '信息' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' }
]
const SEVERITY_FILTER_OPTS = [
  { value: '', label: '全部' },
  { value: 'info', label: '信息' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' }
]

function blankForm() {
  return {
    name: '',
    metric: 'temperature',
    operator: 'gt',
    threshold: 35,
    logic: 'none',
    second_metric: 'temperature',
    second_operator: 'gt',
    second_threshold: 0,
    severity: 'warning',
    enabled: true,
    notify: false,
    targetKeys: []
  }
}

const dialog = reactive({
  visible: false,
  edit: null,
  loading: false,
  form: blankForm()
})

function canEdit(rule) {
  if (user.isAdmin) return true
  return rule && rule.user_id === user.user?.id
}

const showGradualBlur = computed(() => records.value.length > 8)

// ============ 加载 ============
async function loadStats() {
  try {
    const s = await alertStats()
    stats.value = {
      counts: s.counts || { info: 0, warning: 0, critical: 0 },
      total: s.total || 0,
      recent: s.recent || []
    }
    statsLoaded.value = true
  } catch (e) {}
}

async function loadRules() {
  try {
    rules.value = await listRules() || []
  } catch (e) {}
}

async function loadRecords() {
  loading.value = true
  try {
    const res = await listRecords({
      page: recForm.page,
      size: recForm.size,
      severity: recForm.severity || undefined
    })
    if (Array.isArray(res)) {
      records.value = res
      recTotal.value = res.length
    } else {
      records.value = res.items || []
      recTotal.value = res.total || 0
    }
  } catch (e) {} finally {
    loading.value = false
  }
}

async function loadTree() {
  try {
    const gws = await listGateways()
    const tree = await Promise.all(
      gws.map(async (gw) => {
        const devs = await listDevices(gw.id).catch(() => [])
        return { ...gw, devices: devs || [] }
      })
    )
    gatewayTree.value = tree
  } catch (e) {}
}

// ============ 规则 CRUD ============
function openCreate() {
  dialog.edit = null
  dialog.form = blankForm()
  // 默认选中所有网关
  dialog.form.targetKeys = gatewayTree.value.map((g) => 'gw_' + g.id)
  dialog.visible = true
}

function openEdit(rule) {
  dialog.edit = rule
  const f = blankForm()
  Object.assign(f, {
    name: rule.name,
    metric: rule.metric,
    operator: rule.operator,
    threshold: rule.threshold,
    logic: rule.logic || 'none',
    second_metric: rule.second_metric || 'temperature',
    second_operator: rule.second_operator || 'gt',
    second_threshold: rule.second_threshold ?? 0,
    severity: rule.severity,
    enabled: rule.enabled,
    notify: !!rule.notify,
    targetKeys: []
  })
  // 从 targets 反推 targetKeys
  if (Array.isArray(rule.targets)) {
    rule.targets.forEach((t) => {
      if (t.device_id === null || t.device_id === undefined) {
        f.targetKeys.push('gw_' + t.gateway_id)
      } else {
        f.targetKeys.push('dev_' + t.device_id)
      }
    })
  }
  dialog.form = f
  dialog.visible = true
}

function targetsFromKeys(keys) {
  const out = []
  const seen = new Set()
  keys.forEach((k) => {
    if (k.startsWith('gw_')) {
      const gid = Number(k.slice(3))
      // 仅当该网关下没有被单独选中的设备时,才添加整网关目标
      const gw = gatewayTree.value.find((g) => g.id === gid)
      const hasSpecific = (gw?.devices || []).some((d) => keys.includes('dev_' + d.id))
      if (!hasSpecific) {
        const key = 'gw:' + gid
        if (!seen.has(key)) { seen.add(key); out.push({ gateway_id: gid, device_id: null }) }
      }
    } else if (k.startsWith('dev_')) {
      const did = Number(k.slice(4))
      // 找到该设备所属网关
      for (const gw of gatewayTree.value) {
        if ((gw.devices || []).find((d) => d.id === did)) {
          const key = 'dev:' + did
          if (!seen.has(key)) {
            seen.add(key)
            out.push({ gateway_id: gw.id, device_id: did })
          }
          break
        }
      }
    }
  })
  return out
}

async function saveRule() {
  if (!dialog.form.name?.trim()) {
    ui.pushToast({ type: 'warning', title: '请输入规则名称' })
    return
  }
  if (dialog.form.threshold === '' || dialog.form.threshold === null || isNaN(Number(dialog.form.threshold))) {
    ui.pushToast({ type: 'warning', title: '请输入阈值' })
    return
  }
  if (dialog.form.logic !== 'none' && (dialog.form.second_threshold === '' || dialog.form.second_threshold === null || isNaN(Number(dialog.form.second_threshold)))) {
    ui.pushToast({ type: 'warning', title: '请输入第二条件阈值' })
    return
  }

  const payload = {
    name: dialog.form.name.trim(),
    metric: dialog.form.metric,
    operator: dialog.form.operator,
    threshold: Number(dialog.form.threshold),
    logic: dialog.form.logic,
    severity: dialog.form.severity,
    enabled: dialog.form.enabled,
    notify: dialog.form.notify,
    targets: targetsFromKeys(dialog.form.targetKeys)
  }
  if (dialog.form.logic !== 'none') {
    payload.second_metric = dialog.form.second_metric
    payload.second_operator = dialog.form.second_operator
    payload.second_threshold = Number(dialog.form.second_threshold)
  }

  dialog.loading = true
  try {
    if (dialog.edit) {
      await updateRule(dialog.edit.id, payload)
      ui.pushToast({ type: 'success', title: '规则已更新' })
    } else {
      await createRule(payload)
      ui.pushToast({ type: 'success', title: '规则已创建' })
    }
    dialog.visible = false
    await loadRules()
    await loadStats()
  } catch (e) {} finally {
    dialog.loading = false
  }
}

const confirmDialog = reactive({
  visible: false,
  title: '',
  message: '',
  action: null,
  loading: false
})

function askRemoveRule(rule) {
  confirmDialog.title = '删除规则'
  confirmDialog.message = `确定删除规则「${rule.name}」?此操作不可撤销。`
  confirmDialog.action = async () => {
    await deleteRule(rule.id)
    ui.pushToast({ type: 'success', title: '已删除' })
    await loadRules()
    await loadStats()
  }
  confirmDialog.visible = true
}

async function runConfirm() {
  if (!confirmDialog.action) return
  confirmDialog.loading = true
  try {
    await confirmDialog.action()
    confirmDialog.visible = false
  } catch (e) {} finally {
    confirmDialog.loading = false
  }
}

async function onToggle(rule) {
  const origin = rule.enabled
  try {
    await toggleRule(rule.id, rule.enabled)
    ui.pushToast({ type: 'success', title: rule.enabled ? '已启用' : '已停用' })
  } catch (e) {
    rule.enabled = origin
  }
}

// ============ 设备树 checkbox ============
function toggleGateway(gw) {
  const gwKey = 'gw_' + gw.id
  const devKeys = (gw.devices || []).map((d) => 'dev_' + d.id)
  const allSelected = dialog.form.targetKeys.includes(gwKey)
  if (allSelected) {
    // 取消整网关 → 转为单独选择所有设备?不,直接移除整网关 + 所有设备键
    dialog.form.targetKeys = dialog.form.targetKeys.filter((k) => k !== gwKey && !devKeys.includes(k))
  } else {
    // 选中整网关 (移除单独设备键,因为整网关已覆盖)
    dialog.form.targetKeys = dialog.form.targetKeys.filter((k) => !devKeys.includes(k))
    if (!dialog.form.targetKeys.includes(gwKey)) dialog.form.targetKeys.push(gwKey)
  }
}

function toggleDevice(gw, dev) {
  const devKey = 'dev_' + dev.id
  const gwKey = 'gw_' + gw.id
  const idx = dialog.form.targetKeys.indexOf(devKey)
  if (idx >= 0) {
    dialog.form.targetKeys.splice(idx, 1)
  } else {
    // 添加设备 → 如果整网关已选,则取消整网关,转为显式选择所有设备
    if (dialog.form.targetKeys.includes(gwKey)) {
      dialog.form.targetKeys = dialog.form.targetKeys.filter((k) => k !== gwKey)
      ;(gw.devices || []).forEach((d) => {
        const k = 'dev_' + d.id
        if (!dialog.form.targetKeys.includes(k)) dialog.form.targetKeys.push(k)
      })
    } else {
      dialog.form.targetKeys.push(devKey)
    }
  }
}

function isGwFullySelected(gw) {
  return dialog.form.targetKeys.includes('gw_' + gw.id)
}
function isGwPartiallySelected(gw) {
  if (isGwFullySelected(gw)) return false
  return (gw.devices || []).some((d) => dialog.form.targetKeys.includes('dev_' + d.id))
}
function isDevSelected(dev) {
  // 整网关选中时,设备也视为选中
  return dialog.form.targetKeys.includes('dev_' + dev.id)
}

// ============ 记录分页 ============
const totalPages = computed(() => Math.max(1, Math.ceil(recTotal.value / recForm.size)))
function goPage(p) {
  if (p < 1 || p > totalPages.value || p === recForm.page) return
  recForm.page = p
  loadRecords()
}
watch(() => recForm.severity, () => { recForm.page = 1; loadRecords() })

// ============ WS ============
let socket
let liveTimers = []
function onAlert(p) {
  if (!p) return
  liveAlerts.value.unshift({
    id: Date.now() + Math.random(),
    rule_name: p.rule_name || ('规则#' + p.rule_id),
    metric: p.metric,
    value: p.value,
    dev_mac: p.dev_mac,
    severity: p.severity || 'info',
    ts: Date.now()
  })
  if (liveAlerts.value.length > 6) liveAlerts.value.length = 6
  loadStats()
  if (tab.value === 0) loadRecords()
  // 6s 后移除
  const id = liveAlerts.value[0].id
  const t = setTimeout(() => {
    liveAlerts.value = liveAlerts.value.filter((a) => a.id !== id)
  }, 6000)
  liveTimers.push(t)
}

onMounted(async () => {
  await Promise.all([loadStats(), loadRules(), loadRecords(), loadTree()])
  socket = getSocket()
  socket.off('alert', onAlert)
  socket.on('alert', onAlert)
})

onBeforeUnmount(() => {
  if (socket) socket.off('alert', onAlert)
  liveTimers.forEach(clearTimeout)
})

function fmtVal(v) {
  if (v === null || v === undefined) return '—'
  const n = Number(v)
  return isNaN(n) ? String(v) : n.toFixed(1)
}

function fmtTime(s) {
  if (!s) return '—'
  return String(s).replace('T', ' ').slice(0, 19)
}
</script>

<template>
  <div class="alerts page-container">
    <PageHeader
      title="告警中心"
      eyebrow="ALERTS"
      :rotating-words="['规则配置', '实时告警', '历史记录']"
    />

    <!-- 实时告警队列 -->
    <TransitionGroup name="live" tag="div" class="live-queue">
      <div
        v-for="a in liveAlerts"
        :key="a.id"
        class="live-alert"
        :style="{ background: SEVERITY_META[a.severity]?.bg, borderColor: SEVERITY_META[a.severity]?.color + '40' }"
      >
        <span class="live-dot" :style="{ background: SEVERITY_META[a.severity]?.color }" />
        <div class="live-body">
          <span class="live-name">{{ a.rule_name }}</span>
          <span class="live-detail">
            <span class="data-value">{{ METRIC_LABELS[a.metric] || a.metric }}</span>
            <span style="opacity:0.6">=</span>
            <b :style="{ color: SEVERITY_META[a.severity]?.color }">{{ fmtVal(a.value) }}</b>
            <span v-if="a.dev_mac" style="opacity:0.5">· {{ a.dev_mac }}</span>
          </span>
        </div>
        <span class="live-tag" :style="{ color: SEVERITY_META[a.severity]?.color }">
          {{ SEVERITY_META[a.severity]?.label }}
        </span>
      </div>
    </TransitionGroup>

    <!-- 统计行 -->
    <div class="stats-grid">
      <GlassStat
        label="告警总数"
        :value="stats.total"
        unit="条"
        eyebrow="TOTAL"
        icon="bell"
        accent="sage"
        :loaded="statsLoaded"
      />
      <GlassStat
        label="信息"
        :value="stats.counts.info"
        unit="条"
        eyebrow="INFO"
        icon="info"
        accent="teal"
        :loaded="statsLoaded"
      />
      <GlassStat
        label="警告"
        :value="stats.counts.warning"
        unit="条"
        eyebrow="WARNING"
        icon="warning"
        accent="amber"
        :loaded="statsLoaded"
      />
      <GlassStat
        label="严重"
        :value="stats.counts.critical"
        unit="条"
        eyebrow="CRITICAL"
        icon="danger"
        accent="danger"
        :loaded="statsLoaded"
      />
    </div>

    <GlassTabs
      v-model="tab"
      :tabs="[
        { name: 'records', label: '告警记录' },
        { name: 'rules', label: `规则配置 · ${rules.length}` }
      ]"
    />

    <!-- Tab 0: 告警记录 -->
    <div v-show="tab === 0" class="tab-pane">
      <div class="rec-toolbar">
        <GlassSelect
          v-model="recForm.severity"
          :options="SEVERITY_FILTER_OPTS"
          class="sev-filter"
        />
        <span class="rec-count">共 {{ recTotal }} 条</span>
      </div>

      <div v-if="loading" class="rec-loading">
        <div v-for="i in 5" :key="i" class="glass-skeleton" style="height: 56px; border-radius: 8px; margin-bottom: 8px" />
      </div>

      <div v-else-if="!records.length" class="empty-wrap">
        <GlassEmpty
          icon="bell"
          title="无告警记录"
          description="尚未触发任何告警,系统将在规则命中时自动记录。"
          :decorative="false"
        />
      </div>

      <div v-else class="rec-list-wrap">
        <FadeContent
          v-for="(r, i) in records"
          :key="r.id || i"
          :distance="16"
          :delay="Math.min(i * 0.03, 0.3)"
        >
          <div class="rec-row">
            <span class="rec-sev-dot" :style="{ background: SEVERITY_META[r.detail_obj?.severity]?.color || '#6b7280' }" />
            <div class="rec-body">
              <div class="rec-line1">
                <span class="rec-rule">{{ r.detail_obj?.rule_name || '规则#' + r.detail_obj?.rule_id }}</span>
                <span class="rec-sev-tag" :style="{ background: SEVERITY_META[r.detail_obj?.severity]?.bg, color: SEVERITY_META[r.detail_obj?.severity]?.color }">
                  {{ SEVERITY_META[r.detail_obj?.severity]?.label || r.detail_obj?.severity }}
                </span>
              </div>
              <div class="rec-line2">
                <span class="data-value">{{ METRIC_LABELS[r.detail_obj?.metric] || r.detail_obj?.metric }}</span>
                <span class="rec-val">{{ fmtVal(r.detail_obj?.value) }}</span>
                <span v-if="r.detail_obj?.dev_mac" class="rec-mac">· {{ r.detail_obj.dev_mac }}</span>
              </div>
            </div>
            <span class="rec-time data-value">{{ fmtTime(r.created_at) }}</span>
          </div>
        </FadeContent>

        <GradualBlur
          v-if="showGradualBlur"
          position="bottom"
          :div-count="6"
          :blur="6"
          size="100px"
          class="rec-gradual"
        />
      </div>

      <!-- 分页 -->
      <div v-if="recTotal > recForm.size" class="pager">
        <button
          class="page-btn"
          data-cursor-target
          aria-label="上一页"
          :disabled="recForm.page <= 1"
          @click="goPage(recForm.page - 1)"
        >
          <Icon name="chevronLeft" :size="14" />
        </button>
        <span class="page-info data-value">{{ recForm.page }} / {{ totalPages }}</span>
        <button
          class="page-btn"
          data-cursor-target
          aria-label="下一页"
          :disabled="recForm.page >= totalPages"
          @click="goPage(recForm.page + 1)"
        >
          <Icon name="chevronRight" :size="14" />
        </button>
      </div>
    </div>

    <!-- Tab 1: 规则配置 -->
    <div v-show="tab === 1" class="tab-pane">
      <div class="rules-toolbar">
        <p class="eyebrow">RULES · {{ rules.length }}</p>
        <button class="glass-btn glass-btn--primary" data-cursor-target @click="openCreate">
          <Icon name="plus" :size="14" /> 新建规则
        </button>
      </div>

      <div v-if="!rules.length" class="empty-wrap">
        <GlassEmpty
          icon="shield"
          title="尚未配置规则"
          description="创建告警规则,设定阈值与触发条件,系统将自动监控传感器数据。"
          :decorative="false"
        >
          <template #action>
            <button class="glass-btn glass-btn--primary" data-cursor-target @click="openCreate">
              <Icon name="plus" :size="14" /> 新建规则
            </button>
          </template>
        </GlassEmpty>
      </div>

      <div v-else class="rules-grid">
        <FadeContent
          v-for="(rule, i) in rules"
          :key="rule.id"
          :distance="24"
          :delay="Math.min(i * 0.04, 0.3)"
        >
          <GlassCard padding="p-5" class="rule-card" :class="{ disabled: !rule.enabled }">
            <div class="rule-head">
              <div class="min-w-0">
                <div class="rule-name">{{ rule.name }}</div>
                <div class="rule-cond">
                  <span class="data-value">{{ METRIC_LABELS[rule.metric] || rule.metric }}</span>
                  <span class="op">{{ OP_LABELS[rule.operator] || rule.operator }}</span>
                  <b>{{ fmtVal(rule.threshold) }}</b>
                  <template v-if="rule.logic && rule.logic !== 'none'">
                    <span class="logic">{{ rule.logic }}</span>
                    <span class="data-value">{{ METRIC_LABELS[rule.second_metric] || rule.second_metric }}</span>
                    <span class="op">{{ OP_LABELS[rule.second_operator] || rule.second_operator }}</span>
                    <b>{{ fmtVal(rule.second_threshold) }}</b>
                  </template>
                </div>
              </div>
              <span class="rule-sev" :style="{ background: SEVERITY_META[rule.severity]?.bg, color: SEVERITY_META[rule.severity]?.color }">
                {{ SEVERITY_META[rule.severity]?.label }}
              </span>
            </div>

            <div class="rule-meta">
              <span class="rule-targets">
                <Icon name="layers" :size="11" />
                {{ (rule.targets || []).length }} 个目标
              </span>
              <span v-if="rule.notify" class="rule-notify">
                <Icon name="mail" :size="11" /> 通知
              </span>
            </div>

            <div class="rule-actions">
              <button
                class="toggle-pill"
                :class="{ on: rule.enabled }"
                :disabled="!canEdit(rule)"
                data-cursor-target
                @click="rule.enabled = !rule.enabled; onToggle(rule)"
              >
                <span class="toggle-dot" />
                <span>{{ rule.enabled ? '启用' : '停用' }}</span>
              </button>
              <button
                class="glass-btn glass-btn-sm"
                :disabled="!canEdit(rule)"
                data-cursor-target
                @click="openEdit(rule)"
              >
                <Icon name="edit" :size="12" /> 编辑
              </button>
              <button
                class="glass-btn glass-btn-danger glass-btn-sm"
                :disabled="!canEdit(rule)"
                data-cursor-target
                @click="askRemoveRule(rule)"
              >
                <Icon name="trash" :size="12" /> 删除
              </button>
            </div>
          </GlassCard>
        </FadeContent>
      </div>
    </div>

    <!-- 规则弹窗 -->
    <GlassModal
      v-model="dialog.visible"
      :title="dialog.edit ? '编辑规则' : '新建规则'"
      size="lg"
    >
      <div class="form-grid">
        <div class="form-col-span-2">
          <GlassInput v-model="dialog.form.name" label="规则名称" placeholder="如:高温告警" maxlength="40" />
        </div>

        <GlassSelect v-model="dialog.form.metric" :options="METRIC_OPTS" label="主指标" />
        <GlassSelect v-model="dialog.form.operator" :options="OPERATOR_OPTS" label="运算符" />
        <div>
          <label class="block mb-1.5 text-sm font-medium" style="color: var(--text-secondary)">阈值</label>
          <GlassInput v-model="dialog.form.threshold" type="number" placeholder="35" />
        </div>
        <GlassSelect v-model="dialog.form.severity" :options="SEVERITY_OPTS" label="严重级别" />

        <GlassSelect v-model="dialog.form.logic" :options="LOGIC_OPTS" label="组合逻辑" />
        <div v-if="dialog.form.logic !== 'none'" class="form-col-span-3 dual-row">
          <GlassSelect v-model="dialog.form.second_metric" :options="METRIC_OPTS" label="次指标" />
          <GlassSelect v-model="dialog.form.second_operator" :options="OPERATOR_OPTS" label="次运算符" />
          <div>
            <label class="block mb-1.5 text-sm font-medium" style="color: var(--text-secondary)">次阈值</label>
            <GlassInput v-model="dialog.form.second_threshold" type="number" />
          </div>
        </div>

        <div class="form-col-span-2 toggles-row">
          <label
            class="toggle-line"
            role="button"
            tabindex="0"
            aria-label="启用规则"
            data-cursor-target
            @click="dialog.form.enabled = !dialog.form.enabled"
            @keydown.enter="dialog.form.enabled = !dialog.form.enabled"
          >
            <span class="checkbox" :class="{ on: dialog.form.enabled }"><Icon v-if="dialog.form.enabled" name="check" :size="12" /></span>
            <span>启用规则</span>
          </label>
          <label
            class="toggle-line"
            role="button"
            tabindex="0"
            aria-label="邮件通知"
            data-cursor-target
            @click="dialog.form.notify = !dialog.form.notify"
            @keydown.enter="dialog.form.notify = !dialog.form.notify"
          >
            <span class="checkbox" :class="{ on: dialog.form.notify }"><Icon v-if="dialog.form.notify" name="check" :size="12" /></span>
            <span>邮件通知</span>
          </label>
        </div>

        <div class="form-col-span-2">
          <label class="block mb-2 text-sm font-medium" style="color: var(--text-secondary)">
            目标设备 <span class="text-xs ml-1" style="color: var(--text-tertiary)">勾选网关则覆盖其下所有设备</span>
          </label>
          <div class="device-tree">
            <div v-for="gw in gatewayTree" :key="gw.id" class="tree-node">
              <div
                class="tree-row tree-gw"
                role="button"
                tabindex="0"
                :aria-label="`选择网关 ${gw.name || '未命名网关'}`"
                data-cursor-target
                @click="toggleGateway(gw)"
                @keydown.enter="toggleGateway(gw)"
              >
                <span class="checkbox" :class="{ on: isGwFullySelected(gw), partial: isGwPartiallySelected(gw) }">
                  <Icon v-if="isGwFullySelected(gw)" name="check" :size="12" />
                </span>
                <Icon name="gateway" :size="14" style="color: var(--mint)" />
                <span class="tree-label">{{ gw.name || '未命名网关' }}</span>
                <span class="tree-count">{{ gw.devices?.length || 0 }} 设备</span>
              </div>
              <div v-if="gw.devices?.length" class="tree-children">
                <div
                  v-for="dev in gw.devices"
                  :key="dev.id"
                  class="tree-row tree-dev"
                  role="button"
                  tabindex="0"
                  :aria-label="`选择设备 ${dev.name || dev.mac || '设备#' + dev.id}`"
                  data-cursor-target
                  @click="toggleDevice(gw, dev)"
                  @keydown.enter="toggleDevice(gw, dev)"
                >
                  <span class="checkbox" :class="{ on: isDevSelected(dev) }">
                    <Icon v-if="isDevSelected(dev)" name="check" :size="12" />
                  </span>
                  <Icon name="cpu" :size="12" style="color: var(--text-tertiary)" />
                  <span class="tree-label">{{ dev.name || dev.mac || '设备#' + dev.id }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="glass-btn" data-cursor-target @click="dialog.visible = false">取消</button>
        <button class="glass-btn glass-btn--primary" data-cursor-target :disabled="dialog.loading" @click="saveRule">
          <Icon v-if="dialog.loading" name="refresh" :size="13" class="spin" />
          <Icon v-else name="check" :size="13" />
          <span>{{ dialog.edit ? '保存' : '创建' }}</span>
        </button>
      </div>
    </GlassModal>

    <!-- 确认删除弹窗 -->
    <GlassModal v-model="confirmDialog.visible" :title="confirmDialog.title" size="sm">
      <p class="modal-desc">{{ confirmDialog.message }}</p>
      <div class="modal-footer">
        <button class="glass-btn" data-cursor-target @click="confirmDialog.visible = false">取消</button>
        <button class="glass-btn glass-btn-danger" data-cursor-target :disabled="confirmDialog.loading" @click="runConfirm">
          <Icon v-if="confirmDialog.loading" name="refresh" :size="13" class="spin" />
          <Icon v-else name="warning" :size="13" />
          <span>确认删除</span>
        </button>
      </div>
    </GlassModal>
  </div>
</template>

<style scoped>
.alerts { }

/* ===== 实时告警队列 ===== */
.live-queue {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 1.25rem;
}
.live-alert {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-radius: var(--radius-md);
  border: 1px solid;
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  animation: live-pulse 1.2s ease-in-out infinite;
}
@keyframes live-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.4); opacity: 0.6; }
}
.live-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.live-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.live-detail {
  font-size: 12px;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: 'JetBrains Mono', monospace;
}
.live-detail b {
  font-weight: 600;
  font-size: 13px;
}
.live-tag {
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  flex-shrink: 0;
}
.live-enter-active,
.live-leave-active {
  transition: all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.live-enter-from {
  opacity: 0;
  transform: translateY(-12px) scale(0.95);
}
.live-leave-to {
  opacity: 0;
  transform: translateX(20px) scale(0.95);
}

/* ===== 统计 ===== */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}
@media (max-width: 1024px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px)  { .stats-grid { grid-template-columns: 1fr; } }

.tab-pane { margin-top: 1rem; }

/* ===== 记录 ===== */
.rec-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 1rem;
}
.sev-filter { width: 160px; }
.rec-count {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
}
.rec-loading { display: flex; flex-direction: column; gap: 8px; }
.empty-wrap { max-width: 480px; margin: 0 auto; padding: 40px 0; }

.rec-list-wrap {
  position: relative;
  max-height: 560px;
  overflow-y: auto;
  border-radius: var(--radius-lg);
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  padding: 8px;
}
.rec-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  border-bottom: 1px solid var(--glass-border);
  transition: background 0.2s ease;
}
.rec-row:hover { background: rgba(255, 255, 255, 0.03); }
.rec-row:last-child { border-bottom: none; }
.rec-sev-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 6px currentColor;
}
.rec-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.rec-line1 {
  display: flex;
  align-items: center;
  gap: 10px;
}
.rec-rule {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.rec-sev-tag {
  font-size: 9px;
  padding: 2px 8px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.rec-line2 {
  font-size: 11px;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 6px;
  font-family: 'JetBrains Mono', monospace;
}
.rec-val {
  color: var(--text-secondary);
  font-weight: 600;
}
.rec-mac { opacity: 0.6; }
.rec-time {
  font-size: 11px;
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.rec-gradual {
  left: 0; right: 0; bottom: 0;
}

.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 1rem;
}
.page-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}
.page-btn:hover:not(:disabled) {
  border-color: var(--mint);
  color: var(--mint);
}
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
}

/* ===== 规则 ===== */
.rules-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 1rem;
}
.rules-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 14px;
}
.rule-card { height: 100%; }
.rule-card.disabled { opacity: 0.55; }
.rule-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.rule-name {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin-bottom: 6px;
}
.rule-cond {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.rule-cond .op,
.rule-cond .logic {
  font-family: 'JetBrains Mono', monospace;
  color: var(--mint);
  font-weight: 600;
}
.rule-cond .logic {
  background: rgba(52, 211, 153, 0.1);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  text-transform: uppercase;
}
.rule-cond b {
  color: var(--amber);
  font-family: 'JetBrains Mono', monospace;
}
.rule-sev {
  font-size: 9px;
  padding: 3px 10px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  flex-shrink: 0;
}
.rule-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
  font-family: 'JetBrains Mono', monospace;
}
.rule-targets,
.rule-notify {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.rule-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--glass-border);
}
.glass-btn-sm {
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 999px;
}
.toggle-pill {
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 999px;
  border: 1px solid var(--glass-border);
  background: var(--glass-light);
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 11px;
  transition: all 0.2s ease;
  font-family: 'DM Sans', sans-serif;
}
.toggle-pill.on {
  background: rgba(52, 211, 153, 0.12);
  color: var(--mint);
  border-color: rgba(52, 211, 153, 0.3);
}
.toggle-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.toggle-pill.on .toggle-dot {
  box-shadow: 0 0 6px currentColor;
}
.toggle-pill:disabled { opacity: 0.5; cursor: not-allowed; }

/* ===== 弹窗 ===== */
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.form-col-span-2 { grid-column: span 2; }
.form-col-span-3 { grid-column: span 2; }
.dual-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 12px;
  align-items: end;
}
@media (max-width: 600px) {
  .form-grid { grid-template-columns: 1fr; }
  .form-col-span-2, .form-col-span-3 { grid-column: span 1; }
  .dual-row { grid-template-columns: 1fr; }
}
.toggles-row {
  display: flex;
  gap: 24px;
}
.toggle-line {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  user-select: none;
}
.checkbox {
  width: 18px;
  height: 18px;
  border-radius: 5px;
  border: 1.5px solid var(--glass-border);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  background: var(--glass-light);
  color: transparent;
}
.checkbox.on {
  background: rgba(132, 204, 22, 0.18);
  border-color: rgba(132, 204, 22, 0.30);
  color: var(--mint);
}
.checkbox.partial {
  background: rgba(52, 211, 153, 0.2);
  border-color: var(--mint);
}
.checkbox.partial::after {
  content: '';
  width: 8px;
  height: 2px;
  background: var(--mint);
  border-radius: 1px;
}

.device-tree {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: 8px;
  background: var(--glass-light);
}
.tree-node {
  margin-bottom: 4px;
}
.tree-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s ease;
}
.tree-row:hover { background: rgba(255, 255, 255, 0.04); }
.tree-gw {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.tree-dev {
  font-size: 12px;
  color: var(--text-secondary);
  padding-left: 28px;
}
.tree-label { flex: 1; min-width: 0; }
.tree-count {
  font-size: 10px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
}

.modal-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
}
.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }


</style>
