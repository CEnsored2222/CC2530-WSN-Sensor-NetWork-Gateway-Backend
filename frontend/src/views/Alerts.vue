<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listRules, createRule, updateRule, deleteRule, toggleRule, listRecords, alertStats } from '@/api/alert'
import { listGateways } from '@/api/gateway'
import { listDevices } from '@/api/device'
import { useUserStore } from '@/stores/user'
import { getSocket } from '@/ws/socket'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.role === 'admin')

const tab = ref('records')

// ----- 统计 -----
const stats = ref({ counts: { info: 0, warning: 0, critical: 0 }, total: 0, recent: [] })

async function loadStats() {
  try {
    stats.value = await alertStats()
  } catch (e) {}
}

// ----- 规则 -----
const rules = ref([])
const rulesLoading = ref(false)
const dialog = reactive({ visible: false, edit: null, loading: false, form: {} })

const METRIC_OPTS = [
  { value: 'temperature', label: '温度', unit: '°C' },
  { value: 'humidity', label: '湿度', unit: '%' },
  { value: 'light', label: '光照', unit: 'lx' },
]
const OP_OPTS = [
  { value: 'gt', label: '>' },
  { value: 'lt', label: '<' },
  { value: 'gte', label: '≥' },
  { value: 'lte', label: '≤' },
  { value: 'eq', label: '=' },
]
const LOGIC_OPTS = [
  { value: 'none', label: '单条件' },
  { value: 'and', label: '且 AND' },
  { value: 'or', label: '或 OR' },
]
const SEV_OPTS = [
  { value: 'info', label: '信息' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
]

function metaMetric(m) {
  return METRIC_OPTS.find((x) => x.value === m) || { label: m, unit: '' }
}
function metaOp(op) {
  return OP_OPTS.find((x) => x.value === op) || { label: op }
}
const SEV_META = {
  info:     { label: '信息', tone: 'info',     sym: '◇' },
  warning:  { label: '警告', tone: 'warning',  sym: '▲' },
  critical: { label: '严重', tone: 'critical', sym: '✕' },
}

// ----- 设备绑定树(网关→设备) -----
// el-tree 节点 id 用前缀区分: gw_{id} 网关级 / dev_{id} 设备级
const gatewayTree = ref([])
const treeRef = ref(null)
const treeLoading = ref(false)

async function loadGatewayTree() {
  treeLoading.value = true
  try {
    const gws = await listGateways()
    const tree = []
    for (const gw of gws) {
      const devs = await listDevices(gw.id)
      tree.push({
        id: `gw_${gw.id}`,
        label: gw.name || gw.hostname || gw.gw_uuid,
        type: 'gateway',
        gwId: gw.id,
        children: (devs || []).map((d) => ({
          id: `dev_${d.id}`,
          label: d.name || d.mac,
          type: 'device',
          gwId: gw.id,
          devId: d.id,
        })),
      })
    }
    gatewayTree.value = tree
  } finally {
    treeLoading.value = false
  }
}

// targets(后端结构) <-> tree checked keys 转换
function targetsToKeys(targets) {
  const keys = []
  for (const t of targets || []) {
    if (t.device_id === null || t.device_id === undefined) {
      keys.push(`gw_${t.gateway_id}`)
    } else {
      keys.push(`dev_${t.device_id}`)
    }
  }
  return keys
}
function keysToTargets(keys) {
  const targets = []
  const devMap = new Map() // devId -> gwId
  for (const node of gatewayTree.value) {
    for (const child of node.children || []) {
      devMap.set(child.devId, child.gwId)
    }
  }
  for (const k of keys) {
    if (k.startsWith('gw_')) {
      targets.push({ gateway_id: parseInt(k.slice(3)), device_id: null })
    } else if (k.startsWith('dev_')) {
      const devId = parseInt(k.slice(4))
      targets.push({ gateway_id: devMap.get(devId), device_id: devId })
    }
  }
  return targets
}

async function loadRules() {
  rulesLoading.value = true
  try {
    rules.value = await listRules()
  } finally {
    rulesLoading.value = false
  }
}

async function openCreate() {
  dialog.edit = null
  dialog.form = {
    name: '', metric: 'temperature', operator: 'gt', threshold: 35,
    logic: 'none', second_metric: 'humidity', second_operator: 'lt', second_threshold: 30,
    severity: 'warning', enabled: true, notify: false,
    targetKeys: [],  // 设备绑定树选中节点 key
  }
  await loadGatewayTree()
  // 默认预选所有网关(对应"默认绑定全部网关")
  dialog.form.targetKeys = gatewayTree.value.map((n) => n.id)
  dialog.visible = true
  await nextTick()
  syncTreeChecked()
}

async function openEdit(rule) {
  dialog.edit = rule
  dialog.form = {
    name: rule.name, metric: rule.metric, operator: rule.operator, threshold: rule.threshold,
    logic: rule.logic,
    second_metric: rule.second_metric || 'humidity',
    second_operator: rule.second_operator || 'lt',
    second_threshold: rule.second_threshold ?? 0,
    severity: rule.severity, enabled: rule.enabled, notify: !!rule.notify,
    targetKeys: [],
  }
  await loadGatewayTree()
  dialog.form.targetKeys = targetsToKeys(rule.targets)
  dialog.visible = true
  await nextTick()
  syncTreeChecked()
}

// el-tree 选中同步
function syncTreeChecked() {
  if (treeRef.value) {
    treeRef.value.setCheckedKeys(dialog.form.targetKeys || [], false)
  }
}
function onTreeCheck() {
  if (treeRef.value) {
    dialog.form.targetKeys = treeRef.value.getCheckedKeys(false)
  }
}

async function submitRule() {
  const f = dialog.form
  if (!f.name?.trim()) return ElMessage.warning('请输入规则名称')
  if (f.threshold === '' || f.threshold === null) return ElMessage.warning('请输入阈值')
  if (f.logic !== 'none' && (f.second_threshold === '' || f.second_threshold === null)) {
    return ElMessage.warning('请输入第二阈值')
  }
  // 构造提交载荷:把树选中 key 转为 targets
  const payload = {
    name: f.name, metric: f.metric, operator: f.operator, threshold: f.threshold,
    logic: f.logic, severity: f.severity, enabled: f.enabled, notify: f.notify,
  }
  if (f.logic !== 'none') {
    payload.second_metric = f.second_metric
    payload.second_operator = f.second_operator
    payload.second_threshold = f.second_threshold
  }
  payload.targets = keysToTargets(f.targetKeys || [])
  dialog.loading = true
  try {
    if (dialog.edit) {
      await updateRule(dialog.edit.id, payload)
      ElMessage.success('规则已更新')
    } else {
      await createRule(payload)
      ElMessage.success('规则已创建')
    }
    dialog.visible = false
    await loadRules()
    await loadStats()
  } catch (e) {} finally {
    dialog.loading = false
  }
}

async function onToggle(rule) {
  // 注意:el-switch @change 在 v-model 更新后触发,直接使用 rule.enabled
  const next = rule.enabled
  try {
    await toggleRule(rule.id, next)
    ElMessage.success(`规则已${next ? '启用' : '停用'}`)
  } catch (e) {
    rule.enabled = !next
  }
}

async function onDelete(rule) {
  await ElMessageBox.confirm(`确定删除规则 "${rule.name}" 吗?`, '删除规则', {
    confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
  }).catch(() => 'cancel').then(async (v) => {
    if (v === 'cancel') return
    await deleteRule(rule.id)
    ElMessage.success('规则已删除')
    await loadRules()
    await loadStats()
  })
}

// ----- 告警记录 -----
const records = ref([])
const recordsLoading = ref(false)
const recForm = reactive({ page: 1, size: 20, severity: '' })
const recTotal = ref(0)

async function loadRecords() {
  recordsLoading.value = true
  try {
    const params = { page: recForm.page, size: recForm.size }
    if (recForm.severity) params.severity = recForm.severity
    const res = await listRecords(params)
    records.value = res.items || []
    recTotal.value = res.total || 0
  } finally {
    recordsLoading.value = false
  }
}

const recPages = computed(() => Math.max(1, Math.ceil(recTotal.value / recForm.size)))
function gotoRec(p) {
  if (p < 1 || p > recPages.value || p === recForm.page) return
  recForm.page = p
  loadRecords()
}
const recPageList = computed(() => {
  const cur = recForm.page, last = recPages.value
  if (last <= 7) return Array.from({ length: last }, (_, i) => i + 1)
  if (cur <= 4) return [1, 2, 3, 4, 5, '…', last]
  if (cur >= last - 3) return [1, '…', last - 4, last - 3, last - 2, last - 1, last]
  return [1, '…', cur - 1, cur, cur + 1, '…', last]
})
function onRecFilter() { recForm.page = 1; loadRecords() }

function fmtVal(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toFixed(1)
}

// ----- WebSocket:实时告警 -----
const liveAlerts = ref([]) // 新告警浮动队列
function pushLive(a) {
  liveAlerts.value.unshift({ ...a, _uid: Date.now() + Math.random() })
  if (liveAlerts.value.length > 6) liveAlerts.value.pop()
  // 6s 后自动移除
  setTimeout(() => {
    liveAlerts.value = liveAlerts.value.filter((x) => x._uid !== (a._uid || a))
  }, 6000)
  loadStats()
  if (tab.value === 'records') loadRecords()
}

function onSocket() {
  const s = getSocket()
  // 先 off 再 on,避免组件多次挂载导致监听器累积
  s.off('alert').on('alert', (p) => {
    p._uid = Date.now() + Math.random()
    pushLive(p)
  })
}

onMounted(async () => {
  await Promise.all([loadRules(), loadStats(), loadRecords()])
  onSocket()
})

onBeforeUnmount(() => {
  const s = getSocket()
  s.off('alert')
})
</script>

<template>
  <div class="alerts">
    <!-- 顶部:统计概览 -->
    <section class="stat-band">
      <div class="stat-card total rise rise-1">
        <div class="label-eyebrow">告警总数</div>
        <div class="stat-val display mono">{{ stats.total }}</div>
      </div>
      <div class="stat-card sev critical rise rise-2">
        <div class="sev-sym">✕</div>
        <div>
          <div class="label-eyebrow">严重 Critical</div>
          <div class="stat-val display mono">{{ stats.counts.critical }}</div>
        </div>
      </div>
      <div class="stat-card sev warning rise rise-3">
        <div class="sev-sym">▲</div>
        <div>
          <div class="label-eyebrow">警告 Warning</div>
          <div class="stat-val display mono">{{ stats.counts.warning }}</div>
        </div>
      </div>
      <div class="stat-card sev info rise rise-4">
        <div class="sev-sym">◇</div>
        <div>
          <div class="label-eyebrow">信息 Info</div>
          <div class="stat-val display mono">{{ stats.counts.info }}</div>
        </div>
      </div>
    </section>

    <!-- 实时告警浮动条 -->
    <TransitionGroup name="live" tag="div" class="live-stack">
      <div
        v-for="a in liveAlerts"
        :key="a._uid"
        class="live-alert"
        :class="`tone-${a.severity}`"
      >
        <span class="la-sym">{{ SEV_META[a.severity]?.sym }}</span>
        <div class="la-body">
          <div class="la-title">{{ a.rule_name || `规则 #${a.rule_id}` }}</div>
          <div class="la-detail mono">
            {{ metaMetric(a.metric).label }} {{ fmtVal(a.value) }}{{ metaMetric(a.metric).unit }}
            <span class="la-mac" v-if="a.dev_mac">· {{ a.dev_mac }}</span>
          </div>
        </div>
        <span class="la-sev" :class="`tone-${a.severity}`">{{ SEV_META[a.severity]?.label }}</span>
      </div>
    </TransitionGroup>

    <!-- Tab 切换 -->
    <section class="tabs rise rise-2">
      <button class="tab" :class="{ on: tab === 'records' }" @click="tab = 'records'">
        <span class="tab-idx mono">01</span>告警记录
      </button>
      <button class="tab" :class="{ on: tab === 'rules' }" @click="tab = 'rules'">
        <span class="tab-idx mono">02</span>预警规则
      </button>
      <div class="tab-actions" v-if="tab === 'rules'">
        <el-button type="primary" @click="openCreate">+ 新建规则</el-button>
      </div>
    </section>

    <!-- ===== 告警记录 ===== -->
    <section v-if="tab === 'records'" class="panel">
      <div class="filter">
        <div class="filter-item">
          <span class="label-eyebrow">级别</span>
          <select v-model="recForm.severity" class="filter-select" @change="onRecFilter">
            <option value="">全部</option>
            <option v-for="s in SEV_OPTS" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
        <button v-if="recForm.severity" class="filter-clear" @click="recForm.severity = ''; onRecFilter()">清除</button>
      </div>

      <div class="rec-list" v-loading="recordsLoading">
        <article
          v-for="(r, i) in records"
          :key="r.id"
          class="rec-row rise"
          :class="`tone-${r.detail_obj?.severity || 'info'}`"
          :style="{ animationDelay: 0.04 + i * 0.03 + 's' }"
        >
          <div class="rec-rail">
            <div class="rec-node">{{ SEV_META[r.detail_obj?.severity]?.sym || '·' }}</div>
          </div>
          <div class="rec-body">
            <div class="rec-top">
              <span class="rec-name">{{ r.detail_obj?.rule_name || `规则 #${r.detail_obj?.rule_id}` }}</span>
              <span class="rec-sev" :class="`tone-${r.detail_obj?.severity || 'info'}`">
                {{ SEV_META[r.detail_obj?.severity]?.label || '信息' }}
              </span>
            </div>
            <div class="rec-detail mono">
              <span class="rec-metric">{{ metaMetric(r.detail_obj?.metric).label }}</span>
              <span class="rec-op">=</span>
              <span class="rec-val">{{ fmtVal(r.detail_obj?.value) }}{{ metaMetric(r.detail_obj?.metric).unit }}</span>
              <span class="rec-mac muted" v-if="r.detail_obj?.dev_mac">· {{ r.detail_obj.dev_mac }}</span>
            </div>
            <div class="rec-foot">
              <span class="mono rec-time">{{ r.created_at }}</span>
              <span class="mono rec-id">#{{ r.id }}</span>
            </div>
          </div>
        </article>

        <div v-if="!recordsLoading && !records.length" class="empty">
          <div class="empty-icon">∅</div>
          <div class="empty-text muted">无告警记录</div>
        </div>
      </div>

      <div class="pager" v-if="recTotal > recForm.size">
        <button class="pg-btn" :disabled="recForm.page <= 1" @click="gotoRec(recForm.page - 1)">‹</button>
        <template v-for="(p, i) in recPageList" :key="i">
          <span v-if="p === '…'" class="pg-ellipsis">…</span>
          <button v-else class="pg-num" :class="{ active: p === recForm.page }" @click="gotoRec(p)">{{ p }}</button>
        </template>
        <button class="pg-btn" :disabled="recForm.page >= recPages" @click="gotoRec(recForm.page + 1)">›</button>
        <span class="pg-info mono">{{ recForm.page }} / {{ recPages }}</span>
      </div>
    </section>

    <!-- ===== 预警规则 ===== -->
    <section v-if="tab === 'rules'" class="panel">
      <div class="rules-hint muted" v-if="!isAdmin">
        <span class="label-eyebrow">只读模式</span> · 仅管理员可修改规则
      </div>

      <div class="rules-list" v-loading="rulesLoading">
        <article
          v-for="(rule, i) in rules"
          :key="rule.id"
          class="rule-card rise"
          :class="`tone-${rule.severity}`"
          :style="{ animationDelay: 0.04 + i * 0.04 + 's' }"
        >
          <div class="rc-head">
            <div class="rc-name-row">
              <span class="rc-sym">{{ SEV_META[rule.severity]?.sym }}</span>
              <h3 class="rc-name display">{{ rule.name }}</h3>
            </div>
            <div class="rc-actions">
              <el-switch
                v-model="rule.enabled"
                :disabled="!isAdmin"
                @change="onToggle(rule)"
              />
              <button v-if="isAdmin" class="icon-btn" title="编辑" @click="openEdit(rule)">✎</button>
              <button v-if="isAdmin" class="icon-btn danger" title="删除" @click="onDelete(rule)">✕</button>
            </div>
          </div>

          <div class="rc-cond mono">
            <span class="cond-pill">
              <span class="cond-label">{{ metaMetric(rule.metric).label }}</span>
              <span class="cond-op">{{ metaOp(rule.operator).label }}</span>
              <span class="cond-val">{{ rule.threshold }}{{ metaMetric(rule.metric).unit }}</span>
            </span>
            <template v-if="rule.logic !== 'none'">
              <span class="cond-logic" :class="rule.logic">{{ rule.logic.toUpperCase() }}</span>
              <span class="cond-pill">
                <span class="cond-label">{{ metaMetric(rule.second_metric).label }}</span>
                <span class="cond-op">{{ metaOp(rule.second_operator).label }}</span>
                <span class="cond-val">{{ rule.second_threshold }}{{ metaMetric(rule.second_metric).unit }}</span>
              </span>
            </template>
          </div>

          <div class="rc-foot">
            <span class="rc-id mono">#{{ rule.id }}</span>
            <span class="rc-sev-tag" :class="`tone-${rule.severity}`">{{ SEV_META[rule.severity].label }}</span>
            <span class="rc-time mono" v-if="rule.created_at">{{ rule.created_at }}</span>
          </div>
        </article>

        <div v-if="!rulesLoading && !rules.length" class="empty">
          <div class="empty-icon">∅</div>
          <div class="empty-text muted">尚未配置规则</div>
          <el-button type="primary" @click="openCreate">创建第一条规则</el-button>
        </div>
      </div>
    </section>

    <!-- ===== 规则编辑弹窗 ===== -->
    <el-dialog
      v-model="dialog.visible"
      :title="dialog.edit ? '编辑规则' : '新建规则'"
      width="560px"
      :close-on-click-modal="false"
    >
      <div class="form">
        <div class="field">
          <label class="label-eyebrow">规则名称</label>
          <el-input v-model="dialog.form.name" placeholder="如:高温告警" maxlength="64" />
        </div>

        <div class="field">
          <label class="label-eyebrow">主条件</label>
          <div class="cond-row">
            <el-select v-model="dialog.form.metric" style="width:120px">
              <el-option v-for="m in METRIC_OPTS" :key="m.value" :label="m.label" :value="m.value" />
            </el-select>
            <el-select v-model="dialog.form.operator" style="width:90px">
              <el-option v-for="o in OP_OPTS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-input-number v-model="dialog.form.threshold" :controls="false" style="flex:1" />
            <span class="cond-unit mono muted">{{ metaMetric(dialog.form.metric).unit }}</span>
          </div>
        </div>

        <div class="field">
          <label class="label-eyebrow">组合逻辑</label>
          <el-select v-model="dialog.form.logic" style="width:160px">
            <el-option v-for="l in LOGIC_OPTS" :key="l.value" :label="l.label" :value="l.value" />
          </el-select>
        </div>

        <div class="field" v-if="dialog.form.logic !== 'none'">
          <label class="label-eyebrow">第二条件</label>
          <div class="cond-row">
            <el-select v-model="dialog.form.second_metric" style="width:120px">
              <el-option v-for="m in METRIC_OPTS" :key="m.value" :label="m.label" :value="m.value" />
            </el-select>
            <el-select v-model="dialog.form.second_operator" style="width:90px">
              <el-option v-for="o in OP_OPTS" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-input-number v-model="dialog.form.second_threshold" :controls="false" style="flex:1" />
            <span class="cond-unit mono muted">{{ metaMetric(dialog.form.second_metric).unit }}</span>
          </div>
        </div>

        <div class="field">
          <label class="label-eyebrow">告警级别</label>
          <div class="sev-picker">
            <button
              v-for="s in SEV_OPTS"
              :key="s.value"
              class="sev-pick-btn"
              :class="[`tone-${s.value}`, { on: dialog.form.severity === s.value }]"
              @click="dialog.form.severity = s.value"
            >
              <span class="sp-sym">{{ SEV_META[s.value].sym }}</span>
              <span>{{ s.label }}</span>
            </button>
          </div>
        </div>

        <div class="field">
          <label class="label-eyebrow">启用状态</label>
          <el-switch v-model="dialog.form.enabled" />
        </div>

        <div class="field">
          <label class="label-eyebrow">通报设置</label>
          <el-switch v-model="dialog.form.notify" />
          <span class="field-hint muted">开启后,命中规则时右下角弹出通报(3s 自动消失)</span>
        </div>

        <div class="field">
          <label class="label-eyebrow">绑定设备</label>
          <span class="field-hint muted">勾选网关=该网关下所有设备遵循规则;勾选设备=仅该设备遵循规则;可多选</span>
          <div class="bind-tree-wrap" v-loading="treeLoading">
            <el-tree
              ref="treeRef"
              :data="gatewayTree"
              show-checkbox
              check-strictly
              node-key="id"
              :props="{ label: 'label', children: 'children' }"
              empty-text="暂无已绑定网关,请先在网关管理中绑定网关"
              class="bind-tree"
              @check="onTreeCheck"
            />
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.loading" @click="submitRule">
          {{ dialog.edit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.alerts { max-width: 1120px; }

/* —— 顶部统计带 —— */
.stat-band {
  display: grid;
  grid-template-columns: 1.2fr 1fr 1fr 1fr;
  gap: 16px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  display: flex;
  align-items: center;
  gap: 18px;
  position: relative;
  overflow: hidden;
}
.stat-card.total {
  flex-direction: column;
  align-items: flex-start;
  gap: 0;
}
.stat-card.total::before {
  content: '';
  position: absolute;
  top: 0; left: 0;
  width: 40px; height: 2px;
  background: var(--sage);
}
.stat-val {
  font-size: 38px;
  font-weight: 300;
  line-height: 1;
  margin-top: 10px;
  letter-spacing: -0.02em;
}
.stat-card.total .stat-val { margin-top: 10px; }
.sev-sym {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--font-mono);
  font-size: 16px;
  flex-shrink: 0;
}
.stat-card.critical .sev-sym { background: rgba(239, 107, 126, 0.16); color: var(--terra); }
.stat-card.warning  .sev-sym { background: var(--amber-soft); color: var(--amber); }
.stat-card.info     .sev-sym { background: var(--sage-soft); color: var(--sage); }

/* —— 实时告警浮动 —— */
.live-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 24px;
}
.live-alert {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  background: var(--surface-hi);
  border: 1px solid var(--line-strong);
  border-left: 3px solid;
  border-radius: var(--radius);
}
.live-alert.tone-critical { border-left-color: var(--terra); }
.live-alert.tone-warning  { border-left-color: var(--amber); }
.live-alert.tone-info     { border-left-color: var(--sage); }
.la-sym {
  width: 26px; height: 26px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-family: var(--font-mono);
  font-size: 13px;
}
.tone-critical .la-sym { background: rgba(239, 107, 126, 0.18); color: var(--terra); }
.tone-warning  .la-sym { background: var(--amber-soft); color: var(--amber); }
.tone-info     .la-sym { background: var(--sage-soft); color: var(--sage); }
.la-title { font-family: var(--font-display); font-size: 15px; font-weight: 500; }
.la-detail { font-size: 12px; color: var(--ink-3); margin-top: 2px; }
.la-mac { color: var(--ink-4); margin-left: 6px; }
.la-sev {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 3px 10px;
  border-radius: 999px;
}
.la-sev.tone-critical { background: rgba(239, 107, 126, 0.16); color: var(--terra); }
.la-sev.tone-warning  { background: var(--amber-soft); color: var(--amber); }
.la-sev.tone-info     { background: var(--sage-soft); color: var(--sage); }

.live-enter-active, .live-leave-active { transition: all 0.4s var(--ease); }
.live-enter-from { opacity: 0; transform: translateX(-12px); }
.live-leave-to { opacity: 0; transform: translateX(20px); }

/* —— Tab —— */
.tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
}
.tab {
  background: none;
  border: none;
  color: var(--ink-4);
  font-family: var(--font-sans);
  font-size: 14px;
  padding: 14px 20px 14px 0;
  margin-right: 24px;
  cursor: pointer;
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  transition: color 0.2s var(--ease);
}
.tab-idx { font-size: 10px; color: var(--ink-5); letter-spacing: 0.1em; }
.tab:hover { color: var(--ink-2); }
.tab.on { color: var(--ink); }
.tab.on .tab-idx { color: var(--sage); }
.tab.on::after {
  content: '';
  position: absolute;
  left: 0; right: 24px;
  bottom: -1px;
  height: 2px;
  background: var(--sage);
}
.tab-actions { margin-left: auto; padding-bottom: 10px; }

/* —— 通用面板 —— */
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px 26px;
}

/* —— 筛选条 —— */
.filter {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-bottom: 18px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--line);
}
.filter-item { display: flex; align-items: center; gap: 10px; }
.filter-select {
  background: var(--paper);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  padding: 7px 30px 7px 12px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--ink);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath fill='%238993b1' d='M5 6L0 0h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
}
.filter-select:focus { outline: none; border-color: var(--sage); }
.filter-clear {
  border: none; background: transparent;
  color: var(--terra); font-size: 12px;
  margin-left: auto; padding: 6px; cursor: pointer;
}
.filter-clear:hover { text-decoration: underline; }

/* —— 告警记录列表 —— */
.rec-list { display: flex; flex-direction: column; }
.rec-row {
  display: grid;
  grid-template-columns: 36px 1fr auto;
  gap: 14px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
  align-items: flex-start;
}
.rec-rail { display: flex; justify-content: center; padding-top: 2px; }
.rec-node {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--paper-deep);
  color: var(--ink-4);
  border: 1px solid var(--line);
}
.tone-critical .rec-node { background: rgba(239, 107, 126, 0.16); color: var(--terra); border-color: rgba(239, 107, 126, 0.3); }
.tone-warning  .rec-node { background: var(--amber-soft); color: var(--amber); border-color: rgba(245, 163, 92, 0.3); }
.tone-info     .rec-node { background: var(--sage-soft); color: var(--sage); border-color: rgba(77, 214, 193, 0.3); }

.rec-body { min-width: 0; }
.rec-top {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.rec-name {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 500;
}
.rec-sev {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 3px;
}
.rec-sev.tone-critical { background: rgba(239, 107, 126, 0.16); color: var(--terra); }
.rec-sev.tone-warning  { background: var(--amber-soft); color: var(--amber); }
.rec-sev.tone-info     { background: var(--sage-soft); color: var(--sage); }

.rec-detail {
  font-size: 13px;
  margin-top: 6px;
  color: var(--ink-2);
  display: flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}
.rec-metric { color: var(--ink); }
.rec-op { color: var(--ink-4); }
.rec-val { color: var(--sage); font-weight: 500; }
.rec-mac { margin-left: 6px; }
.rec-foot {
  margin-top: 8px;
  display: flex;
  gap: 14px;
  font-size: 11px;
  color: var(--ink-4);
}
.rec-id { margin-left: auto; }

/* —— 规则卡片 —— */
.rules-hint {
  padding: 10px 14px;
  background: var(--sage-tint);
  border-left: 2px solid var(--sage);
  border-radius: 0 var(--radius) var(--radius) 0;
  margin-bottom: 18px;
  font-size: 12px;
}
.rules-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}
.rule-card {
  background: var(--surface-hi);
  border: 1px solid var(--line);
  border-left: 3px solid;
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.rule-card.tone-critical { border-left-color: var(--terra); }
.rule-card.tone-warning  { border-left-color: var(--amber); }
.rule-card.tone-info     { border-left-color: var(--sage); }

.rc-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.rc-name-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
.rc-sym {
  width: 24px; height: 24px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-family: var(--font-mono);
  font-size: 11px;
  flex-shrink: 0;
}
.tone-critical .rc-sym { background: rgba(239, 107, 126, 0.18); color: var(--terra); }
.tone-warning  .rc-sym { background: var(--amber-soft); color: var(--amber); }
.tone-info     .rc-sym { background: var(--sage-soft); color: var(--sage); }

.rc-name {
  font-size: 17px;
  font-weight: 500;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.rc-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.icon-btn {
  background: transparent;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  width: 28px; height: 28px;
  cursor: pointer;
  color: var(--ink-3);
  font-size: 13px;
  transition: all 0.2s var(--ease);
}
.icon-btn:hover { border-color: var(--sage); color: var(--sage); }
.icon-btn.danger:hover { border-color: var(--terra); color: var(--terra); }

.rc-cond {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}
.cond-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--paper-deep);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 5px 10px;
}
.cond-label { color: var(--ink-2); }
.cond-op { color: var(--sage); font-weight: 600; }
.cond-val { color: var(--ink); font-weight: 500; }
.cond-unit { color: var(--ink-4); font-size: 11px; }
.cond-logic {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.08em;
  padding: 3px 8px;
  border-radius: 3px;
}
.cond-logic.and { background: rgba(239, 107, 126, 0.16); color: var(--terra); }
.cond-logic.or  { background: var(--amber-soft); color: var(--amber); }

.rc-foot {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  color: var(--ink-4);
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.rc-sev-tag {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 3px;
}
.rc-sev-tag.tone-critical { background: rgba(239, 107, 126, 0.16); color: var(--terra); }
.rc-sev-tag.tone-warning  { background: var(--amber-soft); color: var(--amber); }
.rc-sev-tag.tone-info     { background: var(--sage-soft); color: var(--sage); }
.rc-time { margin-left: auto; }

/* —— 分页 —— */
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 22px;
  padding-top: 18px;
}
.pg-btn, .pg-num {
  min-width: 30px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  color: var(--ink-2);
  border-radius: var(--radius);
  font-family: var(--font-mono);
  font-size: 12px;
  transition: all 0.2s var(--ease);
}
.pg-btn:hover:not(:disabled), .pg-num:hover:not(.active) {
  border-color: var(--sage); color: var(--sage); background: var(--sage-tint);
}
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-num.active { background: var(--sage); border-color: var(--sage); color: #06141a; }
.pg-ellipsis { color: var(--ink-4); padding: 0 4px; }
.pg-info { margin-left: 14px; font-size: 11px; color: var(--ink-4); }

/* —— 空状态 —— */
.empty { padding: 60px 0; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 14px; }
.empty-icon { font-family: var(--font-display); font-size: 44px; color: var(--line-strong); line-height: 1; }
.empty-text { font-size: 13px; }

/* —— 表单 —— */
.form { display: flex; flex-direction: column; gap: 18px; }
.field label { display: block; margin-bottom: 8px; }
.field-hint { font-size: 12px; margin-left: 12px; }
.field-hint.muted { display: block; margin-left: 0; margin-bottom: 10px; color: var(--ink-4); }

/* —— 绑定设备树(双主题适配) —— */
.bind-tree-wrap {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 10px 12px;
  max-height: 220px;
  overflow-y: auto;
  background: var(--paper);
  transition: border-color 0.2s, background 0.2s;
}
.bind-tree-wrap::-webkit-scrollbar { width: 6px; }
.bind-tree-wrap::-webkit-scrollbar-thumb {
  background: var(--line-strong);
  border-radius: 3px;
}
.bind-tree-wrap::-webkit-scrollbar-track { background: transparent; }

/* el-tree 内部默认带白色背景,需覆盖为透明以继承 wrap */
.bind-tree :deep(.el-tree) {
  background: transparent;
  --el-tree-node-hover-bg-color: var(--sage-tint);
  --el-tree-text-color: var(--ink-2);
  --el-tree-expand-icon-color: var(--ink-3);
}
.bind-tree :deep(.el-tree-node__content) {
  height: 34px;
  border-radius: var(--radius);
  transition: background 0.15s;
}
.bind-tree :deep(.el-tree-node__content:hover) {
  background: var(--sage-tint);
}
.bind-tree :deep(.el-tree-node__content) > .el-tree-node__expand-icon {
  color: var(--ink-3);
}
.bind-tree :deep(.el-tree-node__content) > .el-tree-node__expand-icon:hover {
  color: var(--sage);
}
.bind-tree :deep(.el-tree-node__label) {
  font-size: 13px;
  color: var(--ink-2);
  letter-spacing: 0.01em;
}
.bind-tree :deep(.el-tree__empty-text) {
  color: var(--ink-4);
  font-size: 12px;
}

/* checkbox:未选中态在深色背景下需提亮边框 */
.bind-tree :deep(.el-checkbox__inner) {
  background-color: var(--surface);
  border-color: var(--line-strong);
  border-radius: 3px;
}
.bind-tree :deep(.el-checkbox__inner:hover) {
  border-color: var(--sage);
}
.bind-tree :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background-color: var(--sage);
  border-color: var(--sage);
}
.bind-tree :deep(.el-checkbox__input.is-checked .el-checkbox__inner::after) {
  border-color: var(--paper-deep);
}
/* indeterminate 态(网关半选) */
.bind-tree :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner) {
  background-color: var(--sage);
  border-color: var(--sage);
}
.bind-tree :deep(.el-checkbox__input.is-indeterminate .el-checkbox__inner::before) {
  background-color: var(--paper-deep);
}
/* checkbox label/文字继承主题色 */
.bind-tree :deep(.el-checkbox__label) {
  color: var(--ink-2);
}
.cond-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.cond-unit { font-size: 12px; min-width: 24px; }

.sev-picker {
  display: flex;
  gap: 8px;
}
.sev-pick-btn {
  flex: 1;
  background: var(--paper);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  padding: 10px 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--ink-3);
  transition: all 0.2s var(--ease);
}
.sp-sym {
  width: 20px; height: 20px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-family: var(--font-mono);
  font-size: 10px;
}
.sev-pick-btn.tone-info .sp-sym { background: var(--sage-soft); color: var(--sage); }
.sev-pick-btn.tone-warning .sp-sym { background: var(--amber-soft); color: var(--amber); }
.sev-pick-btn.tone-critical .sp-sym { background: rgba(239, 107, 126, 0.16); color: var(--terra); }
.sev-pick-btn.on { border-color: var(--sage); color: var(--ink); background: var(--sage-tint); }
.sev-pick-btn:hover { border-color: var(--sage); }

@media (max-width: 980px) {
  .stat-band { grid-template-columns: 1fr 1fr; }
  .rules-list { grid-template-columns: 1fr; }
}
</style>
