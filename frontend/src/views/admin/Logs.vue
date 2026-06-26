<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listLogs, listActions, deleteLog, deleteLogsBatch } from '@/api/log'

const loading = ref(false)
const items = ref([])
const total = ref(0)
const actions = ref([])
const form = reactive({
  action: '',
  page: 1,
  size: 20
})
// 多选:选中的日志 id 集合
const selected = ref(new Set())
const deleting = ref(false)

// action 中文标签与归类色映射
const ACTION_META = {
  login:             { label: '登录',     tint: 'sage',  icon: '⌁' },
  approve_gateway:   { label: '审批网关',  tint: 'sage',  icon: '✓' },
  reject_gateway:    { label: '拒绝网关',  tint: 'terra', icon: '×' },
  unbind_gateway:    { label: '解绑网关',  tint: 'terra', icon: '⌫' },
  bind_device:        { label: '绑定设备',  tint: 'sage',  icon: '⊙' },
  device_cmd:         { label: '设备控制',  tint: 'amber', icon: '⌖' },
  toggle_subscription:{ label: '订阅变更',  tint: 'amber', icon: '◐' }
}

function metaOf(action) {
  return ACTION_META[action] || { label: action || '未知', tint: 'ink', icon: '·' }
}

const pages = computed(() => Math.max(1, Math.ceil(total.value / form.size)))

async function load() {
  loading.value = true
  try {
    const params = { page: form.page, size: form.size }
    if (form.action) params.action = form.action
    const res = await listLogs(params)
    items.value = res.items || []
    total.value = res.total || 0
    // 重新加载后清空选择
    selected.value = new Set()
  } finally {
    loading.value = false
  }
}

// ----- 选择 -----
function toggleSelect(id) {
  const s = new Set(selected.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  selected.value = s
}
function selectAll() {
  // 全选当前页
  selected.value = new Set(items.value.map((i) => i.id))
}
function clearSelection() {
  selected.value = new Set()
}
const allSelected = computed(
  () => items.value.length > 0 && items.value.every((i) => selected.value.has(i.id))
)
const someSelected = computed(() => selected.value.size > 0 && !allSelected.value)
function toggleAll() {
  if (allSelected.value) clearSelection()
  else selectAll()
}

// ----- 删除 -----
async function onDelete(log) {
  try {
    await ElMessageBox.confirm(`确定删除该条日志 #${log.id} 吗?`, '删除日志', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  deleting.value = true
  try {
    await deleteLog(log.id)
    ElMessage.success('日志已删除')
    // 若删除后当前页空了,回退一页
    if (items.value.length === 1 && form.page > 1) form.page--
    await load()
  } catch (e) {} finally {
    deleting.value = false
  }
}

async function onDeleteBatch() {
  const ids = Array.from(selected.value)
  if (!ids.length) return
  try {
    await ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条日志吗?`, '批量删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  deleting.value = true
  try {
    const res = await deleteLogsBatch(ids)
    ElMessage.success(`已删除 ${res.deleted || ids.length} 条日志`)
    if (items.value.length === ids.length && form.page > 1) form.page--
    await load()
  } catch (e) {} finally {
    deleting.value = false
  }
}

async function loadActions() {
  try {
    const list = await listActions()
    // 合并已知 action(即使数据库暂未出现也提供筛选项)
    const known = Object.keys(ACTION_META)
    actions.value = Array.from(new Set([...list, ...known]))
  } catch (e) {
    actions.value = Object.keys(ACTION_META)
  }
}

function onFilter() {
  form.page = 1
  load()
}

function goto(p) {
  if (p < 1 || p > pages.value || p === form.page) return
  form.page = p
  load()
}

function fmtTime(t) {
  if (!t) return '—'
  return t
}

// 解析 detail JSON
function parseDetail(d) {
  if (!d) return ''
  try {
    const o = JSON.parse(d)
    return Object.entries(o)
      .map(([k, v]) => `${k}: ${v}`)
      .join('  ')
  } catch {
    return d
  }
}

const pageList = computed(() => {
  const cur = form.page
  const last = pages.value
  if (last <= 7) return Array.from({ length: last }, (_, i) => i + 1)
  if (cur <= 4) return [1, 2, 3, 4, 5, '…', last]
  if (cur >= last - 3) return [1, '…', last - 4, last - 3, last - 2, last - 1, last]
  return [1, '…', cur - 1, cur, cur + 1, '…', last]
})

onMounted(() => {
  loadActions()
  load()
})
</script>

<template>
  <div class="logs">
    <!-- 头部 -->
    <section class="head rise rise-1">
      <div>
        <div class="label-eyebrow">Admin · Operation Logs</div>
        <h2 class="title display">操作日志</h2>
        <p class="head-desc muted">
          记录用户在系统中的关键操作:网关审批、设备绑定、控制指令、订阅变更等。
        </p>
      </div>
      <div class="head-stat">
        <div class="hs-num display mono">{{ total }}<span>条</span></div>
        <div class="label-eyebrow">记录总数</div>
      </div>
    </section>

    <!-- 筛选 -->
    <section class="filter rise rise-2">
      <div class="filter-item">
        <span class="filter-label label-eyebrow">操作类型</span>
        <select v-model="form.action" class="filter-select" @change="onFilter">
          <option value="">全部</option>
          <option v-for="a in actions" :key="a" :value="a">{{ metaOf(a).label }}</option>
        </select>
      </div>
      <button v-if="form.action" class="filter-clear" @click="form.action = ''; onFilter()">清除筛选</button>

      <div class="filter-spacer"></div>

      <!-- 批量操作区 -->
      <div class="batch-bar" :class="{ active: someSelected || allSelected }">
        <label class="batch-check" @click.prevent="toggleAll">
          <span class="cb" :class="{ checked: allSelected, indeterminate: someSelected }"></span>
          <span class="batch-label">{{ allSelected ? '取消全选' : '全选本页' }}</span>
        </label>
        <span class="batch-count mono" v-if="selected.size">已选 {{ selected.size }}</span>
        <button
          class="batch-del"
          :disabled="!selected.size || deleting"
          @click="onDeleteBatch"
        >批量删除</button>
      </div>
    </section>

    <!-- 时间线列表 -->
    <section class="timeline" v-loading="loading">
      <article
        v-for="(log, i) in items"
        :key="log.id"
        class="log-row rise"
        :class="[`tint-${metaOf(log.action).tint}`, { selected: selected.has(log.id) }]"
        :style="{ animationDelay: 0.05 + i * 0.04 + 's' }"
      >
        <!-- 行选择框 -->
        <label class="log-check" @click.prevent="toggleSelect(log.id)">
          <span class="cb" :class="{ checked: selected.has(log.id) }"></span>
        </label>

        <div class="log-rail">
          <div class="log-node">{{ metaOf(log.action).icon }}</div>
          <div class="log-line" v-if="i < items.length - 1"></div>
        </div>

        <div class="log-body">
          <div class="log-top">
            <span class="log-action">{{ metaOf(log.action).label }}</span>
            <span class="log-code mono">{{ log.action }}</span>
          </div>
          <div class="log-detail muted" v-if="parseDetail(log.detail)">
            {{ parseDetail(log.detail) }}
          </div>
          <div class="log-foot">
            <span class="log-user">
              <span class="log-avatar">{{ (log.username || '?').slice(0, 1).toUpperCase() }}</span>
              {{ log.username || '系统' }}
            </span>
            <span class="log-sep">·</span>
            <span class="log-target mono" v-if="log.target_type">
              {{ log.target_type }}<template v-if="log.target_id"> #{{ log.target_id }}</template>
            </span>
            <span class="log-sep" v-if="log.target_type">·</span>
            <span class="log-time mono">{{ fmtTime(log.created_at) }}</span>
            <span class="log-ip mono" v-if="log.ip">from {{ log.ip }}</span>
          </div>
        </div>

        <div class="log-tail">
          <div class="log-id mono">#{{ log.id }}</div>
          <button
            class="log-del"
            :disabled="deleting"
            @click="onDelete(log)"
            title="删除该日志"
          >删除</button>
        </div>
      </article>

      <div v-if="!loading && !items.length" class="empty">
        <div class="empty-icon">∅</div>
        <div class="empty-text muted">暂无操作记录</div>
      </div>
    </section>

    <!-- 分页 -->
    <section class="pager rise rise-3" v-if="total > form.size">
      <button class="pg-btn" :disabled="form.page <= 1" @click="goto(form.page - 1)">‹</button>
      <template v-for="(p, i) in pageList" :key="i">
        <span v-if="p === '…'" class="pg-ellipsis">…</span>
        <button v-else class="pg-num" :class="{ active: p === form.page }" @click="goto(p)">{{ p }}</button>
      </template>
      <button class="pg-btn" :disabled="form.page >= pages" @click="goto(form.page + 1)">›</button>
      <span class="pg-info mono">{{ form.page }} / {{ pages }}</span>
    </section>
  </div>
</template>

<style scoped>
.logs { max-width: 1080px; }

/* —— 头部 —— */
.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 26px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
}
.title { font-size: 28px; font-weight: 400; letter-spacing: -0.02em; margin-top: 6px; }
.head-desc { font-size: 13px; line-height: 1.7; max-width: 520px; margin-top: 10px; }
.head-stat { text-align: right; }
.hs-num {
  font-size: 44px;
  font-weight: 300;
  line-height: 1;
  letter-spacing: -0.03em;
}
.hs-num span { color: var(--ink-4); font-size: 14px; margin-left: 4px; }

/* —— 筛选条 —— */
.filter {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 22px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  margin-bottom: 26px;
}
.filter-item { display: flex; align-items: center; gap: 10px; }
.filter-label { color: var(--ink-4); }
.filter-select {
  background: var(--paper);
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  padding: 8px 32px 8px 14px;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--ink);
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath fill='%236b665e' d='M5 6L0 0h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  transition: border-color 0.22s var(--ease);
}
.filter-select:hover { border-color: var(--sage); }
.filter-select:focus { outline: none; border-color: var(--sage); }
.filter-clear {
  border: none;
  background: transparent;
  color: var(--terra);
  font-size: 12px;
  letter-spacing: 0.04em;
  padding: 6px 4px;
  margin-left: auto;
}
.filter-clear:hover { text-decoration: underline; }

/* —— 时间线 —— */
.timeline { display: flex; flex-direction: column; }
.log-row {
  display: grid;
  grid-template-columns: 24px 40px 1fr auto;
  gap: 16px;
  padding: 18px 4px 18px 0;
  border-bottom: 1px solid var(--line);
  position: relative;
  transition: background 0.2s var(--ease);
}
.log-row.selected {
  background: var(--sage-tint);
}
.log-row:hover .log-del {
  opacity: 1;
}
.log-rail {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 2px;
}
.log-node {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--font-mono);
  font-size: 13px;
  background: var(--paper-deep);
  color: var(--ink-3);
  border: 1px solid var(--line);
  flex-shrink: 0;
  z-index: 1;
  transition: all 0.3s var(--ease);
}
.log-line {
  position: absolute;
  top: 30px;
  bottom: -18px;
  width: 1px;
  background: var(--line);
}

/* 色彩归类 */
.tint-sage .log-node { background: var(--sage-soft); color: var(--sage-deep); border-color: var(--sage); }
.tint-amber .log-node { background: var(--amber-soft); color: var(--amber); border-color: var(--amber); }
.tint-terra .log-node { background: #f7e6e1; color: var(--terra); border-color: var(--terra); }

.log-body { min-width: 0; }
.log-top {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.log-action {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.log-code {
  font-size: 10px;
  color: var(--ink-4);
  letter-spacing: 0.06em;
  padding: 2px 7px;
  background: var(--paper-deep);
  border-radius: 3px;
}
.log-detail {
  font-size: 13px;
  line-height: 1.6;
  margin-top: 6px;
  font-family: var(--font-mono);
  word-break: break-all;
}
.log-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--ink-4);
  flex-wrap: wrap;
}
.log-user {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ink-2);
  font-weight: 500;
}
.log-avatar {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--sage);
  color: #fff;
  display: grid;
  place-items: center;
  font-size: 10px;
  font-family: var(--font-display);
}
.log-sep { color: var(--ink-5); }
.log-target {
  letter-spacing: 0.02em;
  color: var(--ink-3);
}
.log-time { color: var(--ink-3); }
.log-ip { color: var(--ink-4); margin-left: auto; }

.log-tail {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  padding-top: 6px;
}
.log-id {
  font-size: 10px;
  color: var(--ink-5);
  letter-spacing: 0.04em;
}
.log-del {
  border: 1px solid var(--line-strong);
  background: transparent;
  color: var(--ink-4);
  font-size: 11px;
  letter-spacing: 0.04em;
  padding: 4px 10px;
  border-radius: var(--radius);
  cursor: pointer;
  opacity: 0;
  transition: all 0.2s var(--ease);
}
.log-del:hover:not(:disabled) {
  border-color: var(--terra);
  color: var(--terra);
  background: rgba(239, 107, 126, 0.06);
  opacity: 1;
}
.log-del:disabled { cursor: not-allowed; opacity: 0.4; }

/* —— 行选择框 —— */
.log-check {
  display: flex;
  align-items: flex-start;
  padding-top: 8px;
  cursor: pointer;
}
.cb {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1.5px solid var(--line-strong);
  background: var(--paper);
  display: inline-block;
  position: relative;
  transition: all 0.2s var(--ease);
  flex-shrink: 0;
}
.cb.checked {
  background: var(--sage);
  border-color: var(--sage);
}
.cb.checked::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 1px;
  width: 5px;
  height: 9px;
  border: solid #06141a;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
.cb.indeterminate {
  background: var(--sage);
  border-color: var(--sage);
}
.cb.indeterminate::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 6px;
  width: 8px;
  height: 2px;
  background: #06141a;
  border-radius: 1px;
}

/* —— 批量操作栏 —— */
.filter-spacer { flex: 1; }
.batch-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding-left: 16px;
  border-left: 1px solid var(--line);
  opacity: 0.55;
  transition: opacity 0.2s var(--ease);
}
.batch-bar.active { opacity: 1; }
.batch-check {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
}
.batch-label {
  font-size: 12px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}
.batch-count {
  font-size: 11px;
  color: var(--sage-deep);
  background: var(--sage-soft);
  padding: 2px 8px;
  border-radius: 10px;
}
.batch-del {
  border: 1px solid var(--terra);
  background: transparent;
  color: var(--terra);
  font-size: 12px;
  letter-spacing: 0.04em;
  padding: 6px 14px;
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s var(--ease);
}
.batch-del:hover:not(:disabled) {
  background: var(--terra);
  color: #fff;
}
.batch-del:disabled {
  border-color: var(--line-strong);
  color: var(--ink-5);
  cursor: not-allowed;
}

/* hover 微反馈 */
.log-row:hover .log-node {
  transform: scale(1.08);
}
.log-row:hover .log-action {
  color: var(--sage-deep);
}

/* —— 空状态 —— */
.empty {
  padding: 60px 0;
  text-align: center;
}
.empty-icon {
  font-family: var(--font-display);
  font-size: 48px;
  color: var(--line-strong);
  line-height: 1;
}
.empty-text { margin-top: 14px; font-size: 13px; }

/* —— 分页 —— */
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 32px;
  padding-top: 22px;
}
.pg-btn, .pg-num {
  min-width: 32px;
  height: 32px;
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
  border-color: var(--sage);
  color: var(--sage-deep);
  background: var(--sage-tint);
}
.pg-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.pg-num.active {
  background: var(--sage);
  border-color: var(--sage);
  color: #fff;
}
.pg-ellipsis {
  color: var(--ink-4);
  padding: 0 4px;
}
.pg-info {
  margin-left: 14px;
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0.06em;
}
</style>
