<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { listLogs, listActions, deleteLog, deleteLogsBatch } from '@/api/log'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassStat from '@/components/layout/GlassStat.vue'
import GlassSelect from '@/components/glass/GlassSelect.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import AnimatedListItem from '@/components/vuebits/AnimatedListItem.vue'
import Icon from '@/components/icons/Icon.vue'

const ui = useUiStore()

const loading = ref(false)
const items = ref([])
const total = ref(0)
const actions = ref([])
const selected = ref(new Set())
const deleting = ref(false)
const expandedId = ref(null)

const form = reactive({ action: '', page: 1, size: 20 })

// 节点配色按操作类型归类（绿色系 + danger + 兜底）
// login/logout -> mint | create/add -> sage | update/config -> teal | delete/remove -> danger | 其他 -> ink
const ACTION_META = {
  login:                { label: '登录',          tint: 'mint',   icon: 'user' },
  register:             { label: '注册',          tint: 'sage',   icon: 'user' },
  send_code:            { label: '发送验证码',    tint: 'teal',   icon: 'mail' },
  approve_gateway:      { label: '审批网关',      tint: 'sage',   icon: 'check' },
  reject_gateway:       { label: '拒绝网关',      tint: 'danger', icon: 'close' },
  unbind_gateway:       { label: '解绑网关',      tint: 'danger', icon: 'unlink' },
  bind_device:          { label: '绑定设备',      tint: 'sage',   icon: 'link' },
  device_cmd:           { label: '设备指令',      tint: 'teal',   icon: 'command' },
  toggle_subscription:  { label: '订阅切换',      tint: 'teal',   icon: 'toggleRight' },
  create_alert_rule:    { label: '创建规则',      tint: 'sage',   icon: 'plus' },
  update_alert_rule:    { label: '更新规则',      tint: 'teal',   icon: 'edit' },
  delete_alert_rule:    { label: '删除规则',      tint: 'danger', icon: 'trash' },
  toggle_alert_rule:    { label: '规则开关',      tint: 'teal',   icon: 'toggleRight' },
  alert:                { label: '告警触发',      tint: 'danger', icon: 'bell' }
}

function actionMeta(a) {
  return ACTION_META[a] || { label: a || '未知', tint: 'ink', icon: 'activity' }
}

const actionOptions = computed(() => {
  const known = Object.keys(ACTION_META)
  const all = Array.from(new Set([...actions.value, ...known]))
  return [{ value: '', label: '全部操作' }, ...all.map((a) => ({ value: a, label: actionMeta(a).label }))]
})

const pages = computed(() => Math.max(1, Math.ceil(total.value / form.size)))

const pageList = computed(() => {
  const last = pages.value
  const cur = form.page
  if (last <= 7) return Array.from({ length: last }, (_, i) => i + 1)
  if (cur <= 4) return [1, 2, 3, 4, 5, '…', last]
  if (cur >= last - 3) return [1, '…', last - 4, last - 3, last - 2, last - 1, last]
  return [1, '…', cur - 1, cur, cur + 1, '…', last]
})

const allSelected = computed(() => items.value.length > 0 && items.value.every((i) => selected.value.has(i.id)))
const someSelected = computed(() => !allSelected.value && items.value.some((i) => selected.value.has(i.id)))
const selectedCount = computed(() => selected.value.size)

function goto(p) {
  if (typeof p !== 'number') return
  if (p < 1 || p > pages.value || p === form.page) return
  form.page = p
  load()
}

function onFilter() {
  form.page = 1
  load()
}

function clearFilter() {
  form.action = ''
  form.page = 1
  load()
}

async function load() {
  loading.value = true
  selected.value = new Set()
  try {
    const res = await listLogs({ page: form.page, size: form.size, action: form.action || undefined })
    if (Array.isArray(res)) {
      items.value = res
      total.value = res.length
    } else {
      items.value = res.items || []
      total.value = res.total || 0
    }
  } catch (e) {} finally {
    loading.value = false
  }
}

async function loadActions() {
  try {
    const list = await listActions()
    actions.value = Array.isArray(list) ? list : (list?.items || [])
  } catch (e) {
    actions.value = Object.keys(ACTION_META)
  }
}

function toggleSelect(id) {
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function toggleAll() {
  if (allSelected.value) {
    selected.value = new Set()
  } else {
    selected.value = new Set(items.value.map((i) => i.id))
  }
}

function toggleExpand(id) {
  expandedId.value = expandedId.value === id ? null : id
}

// 内联展示用的 detail 文本
function parseDetailText(d) {
  if (!d) return ''
  try {
    const obj = typeof d === 'string' ? JSON.parse(d) : d
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      return Object.entries(obj).map(([k, v]) => `${k}: ${v}`).join('  ')
    }
    return String(d)
  } catch {
    return String(d)
  }
}

// 展开时键值网格用的解析
function parseDetail(d) {
  if (!d) return []
  try {
    const obj = typeof d === 'string' ? JSON.parse(d) : d
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      return Object.entries(obj).map(([k, v]) => [k, String(v)])
    }
    return [['raw', String(d)]]
  } catch {
    return [['raw', String(d)]]
  }
}

function fmtTime(s) {
  if (!s) return '—'
  return String(s).replace('T', ' ').slice(0, 19)
}

const confirmDialog = reactive({
  visible: false,
  title: '',
  message: '',
  action: null,
  loading: false
})

function askDelete(item) {
  confirmDialog.title = '删除操作记录'
  confirmDialog.message = `确定删除记录 #${item.id}?此操作不可撤销。`
  confirmDialog.action = async () => {
    await deleteLog(item.id)
    ui.pushToast({ type: 'success', title: '已删除' })
    // 如果删除后当前页空了且 page > 1,回退一页
    if (items.value.length <= 1 && form.page > 1) form.page--
    await load()
  }
  confirmDialog.visible = true
}

function askBatchDelete() {
  if (!selectedCount.value) return
  confirmDialog.title = '批量删除操作记录'
  confirmDialog.message = `确定删除选中的 ${selectedCount.value} 条记录?此操作不可撤销。`
  confirmDialog.action = async () => {
    const ids = Array.from(selected.value)
    const res = await deleteLogsBatch(ids)
    ui.pushToast({ type: 'success', title: '已批量删除', message: `${res?.deleted || ids.length} 条` })
    if (items.value.length === ids.length && form.page > 1) form.page--
    await load()
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

onMounted(async () => {
  await Promise.all([load(), loadActions()])
})
</script>

<template>
  <div class="logs page-container">
    <PageHeader
      title="操作日志"
      eyebrow="AUDIT"
      :rotating-words="['登录', '网关审批', '设备指令', '告警规则', '订阅切换']"
    />

    <div class="stats-grid">
      <GlassStat
        label="总记录数"
        :value="total"
        unit="条"
        eyebrow="TOTAL"
        icon="logs"
        accent="sage"
      />
      <GlassStat
        label="当前页"
        :value="form.page"
        :unit="`/ ${pages}`"
        eyebrow="PAGE"
        icon="layers"
        accent="teal"
      />
      <GlassStat
        label="已选中"
        :value="selectedCount"
        unit="条"
        eyebrow="SELECTED"
        icon="check"
        accent="amber"
      />
      <GlassStat
        label="操作类型"
        :value="actions.length"
        unit="种"
        eyebrow="ACTIONS"
        icon="command"
        accent="mint"
      />
    </div>

    <!-- 工具栏(独立,不包裹在卡片内) -->
    <div class="logs-toolbar">
      <div class="filter-group">
        <GlassSelect
          v-model="form.action"
          :options="actionOptions"
          class="action-filter"
          @update:model-value="onFilter"
        />
        <button v-if="form.action" class="glass-btn glass-btn-sm" data-cursor-target @click="clearFilter">
          <Icon name="close" :size="12" /> 清除
        </button>
      </div>
      <div class="batch-group">
        <button
          class="glass-btn glass-btn-danger glass-btn-sm"
          data-cursor-target
          :disabled="!selectedCount"
          @click="askBatchDelete"
        >
          <Icon name="trash" :size="12" />
          <span>批量删除</span>
          <span v-if="selectedCount" class="batch-count">{{ selectedCount }}</span>
        </button>
      </div>
    </div>

    <!-- 加载骨架 -->
    <div v-if="loading" class="log-loading">
      <div v-for="i in 6" :key="i" class="glass-skeleton" style="height: 64px; border-radius: 8px; margin-bottom: 6px" />
    </div>

    <!-- 空状态 -->
    <div v-else-if="!items.length" class="log-empty">
      <GlassEmpty
        icon="logs"
        title="暂无操作记录"
        description="系统操作将自动记录在此,可按操作类型筛选并审计。"
        :decorative="false"
      />
    </div>

    <!-- 日志滚动区(液态玻璃卡片包裹) -->
    <GlassCard v-else padding="p-0" :hover="false" class="logs-card">
      <div class="logs-scroll-area">
        <div class="logs-list">
          <AnimatedListItem
            v-for="(item, i) in items"
            :key="item.id"
            :y="20"
            :delay="Math.min(i * 0.04, 0.3)"
          >
            <div
              class="log-row"
              :class="[
                `tint-${actionMeta(item.action).tint}`,
                { expanded: expandedId === item.id, selected: selected.has(item.id) }
              ]"
            >
              <!-- 行选择框 -->
              <button class="cell-check" data-cursor-target @click="toggleSelect(item.id)">
                <span class="checkbox" :class="{ on: selected.has(item.id) }">
                  <Icon v-if="selected.has(item.id)" name="check" :size="12" />
                </span>
              </button>

              <!-- 时间 -->
              <span class="log-time">{{ fmtTime(item.created_at) }}</span>

              <!-- 操作标签 -->
              <span class="log-badge" :class="`badge-${actionMeta(item.action).tint}`">
                <Icon :name="actionMeta(item.action).icon" :size="11" />
                {{ actionMeta(item.action).label }}
              </span>

              <!-- 用户 -->
              <span class="log-user">
                <span class="log-avatar">{{ (item.username || '?').slice(0, 1).toUpperCase() }}</span>
                {{ item.username || '系统' }}
              </span>

              <!-- 详情(内联截断) -->
              <span v-if="parseDetailText(item.detail)" class="log-detail-inline">
                {{ parseDetailText(item.detail) }}
              </span>

              <!-- 尾部操作 -->
              <div class="log-tail">
                <span class="log-id">#{{ item.id }}</span>
                <button
                  v-if="item.detail"
                  class="icon-btn"
                  data-cursor-target
                  :class="{ active: expandedId === item.id }"
                  @click="toggleExpand(item.id)"
                >
                  <Icon
                    name="chevronRight"
                    :size="14"
                    :style="{ transform: expandedId === item.id ? 'rotate(90deg)' : 'none', transition: 'transform 0.2s' }"
                  />
                </button>
                <button class="icon-btn danger" data-cursor-target @click="askDelete(item)">
                  <Icon name="trash" :size="14" />
                </button>
              </div>
            </div>

            <Transition name="detail">
              <div v-if="expandedId === item.id && item.detail" class="log-detail">
                <div class="detail-grid">
                  <div v-for="([k, v], idx) in parseDetail(item.detail)" :key="idx" class="detail-item">
                    <span class="detail-key">{{ k }}</span>
                    <span class="detail-val">{{ v }}</span>
                  </div>
                </div>
              </div>
            </Transition>
          </AnimatedListItem>
        </div>
      </div>
    </GlassCard>

    <!-- 分页(独立) -->
    <div v-if="total > form.size" class="pager">
      <button class="page-btn" data-cursor-target :disabled="form.page <= 1" @click="goto(form.page - 1)">
        <Icon name="chevronLeft" :size="14" />
      </button>
      <button
        v-for="(p, i) in pageList"
        :key="i"
        class="page-num"
        :class="{ active: p === form.page, ellipsis: p === '…' }"
        :disabled="p === '…'"
        data-cursor-target
        @click="goto(p)"
      >{{ p }}</button>
      <button class="page-btn" data-cursor-target :disabled="form.page >= pages" @click="goto(form.page + 1)">
        <Icon name="chevronRight" :size="14" />
      </button>
    </div>

    <!-- 确认弹窗 -->
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
.logs {
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 7.5rem);
  height: calc(100dvh - 7.5rem);
  min-height: 400px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 1rem;
  flex-shrink: 0;
}
@media (max-width: 1024px) { .stats-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 480px)  { .stats-grid { grid-template-columns: 1fr; } }

.logs-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 1rem;
  flex-wrap: wrap;
  flex-shrink: 0;
}

/* ===== 滚动区(液态玻璃卡片) ===== */
.logs-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.logs-scroll-area {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.logs-list {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 4px;
  scroll-behavior: smooth;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.action-filter { width: 200px; }
.batch-group { display: flex; gap: 8px; }
.glass-btn-sm {
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.batch-count {
  background: rgba(248, 113, 113, 0.2);
  color: var(--color-danger);
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  font-family: 'JetBrains Mono', monospace;
}

/* ===== 日志行(CSS Grid 固定列宽:复选框 | 时间 | 标签 | 用户 | 详情 | 操作) ===== */
.log-row {
  display: grid;
  grid-template-columns: 32px 140px 110px 130px 1fr 90px;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--glass-border);
  position: relative;
  transition: background 0.18s ease;
}
.log-row > .cell-check      { grid-column: 1; }
.log-row > .log-time        { grid-column: 2; }
.log-row > .log-badge       { grid-column: 3; }
.log-row > .log-user        { grid-column: 4; }
.log-row > .log-detail-inline { grid-column: 5; }
.log-row > .log-tail        { grid-column: 6; }
.log-row:hover { background: var(--glass-light); }
.log-row.selected {
  background: color-mix(in srgb, var(--sage) 8%, transparent);
}
.log-row.expanded {
  background: color-mix(in srgb, var(--mint) 6%, transparent);
  border-bottom-color: color-mix(in srgb, var(--mint) 30%, transparent);
}

/* 时间 */
.log-time {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}

/* 操作标签 */
.log-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  white-space: nowrap;
  flex-shrink: 0;
  border: 1px solid transparent;
  letter-spacing: 0.01em;
}
.badge-mint {
  background: color-mix(in srgb, var(--mint) 14%, transparent);
  color: var(--mint);
  border-color: color-mix(in srgb, var(--mint) 30%, transparent);
}
.badge-sage {
  background: color-mix(in srgb, var(--sage) 14%, transparent);
  color: var(--sage);
  border-color: color-mix(in srgb, var(--sage) 30%, transparent);
}
.badge-teal {
  background: color-mix(in srgb, var(--teal) 14%, transparent);
  color: var(--teal);
  border-color: color-mix(in srgb, var(--teal) 30%, transparent);
}
.badge-danger {
  background: color-mix(in srgb, var(--color-danger) 14%, transparent);
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 30%, transparent);
}
.badge-ink {
  background: var(--glass-light);
  color: var(--text-tertiary);
  border-color: var(--glass-border);
}

/* 用户 */
.log-user {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  white-space: nowrap;
  flex-shrink: 0;
}
.log-avatar {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--sage), var(--teal));
  color: #04140c;
  display: grid;
  place-items: center;
  font-size: 10px;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}

/* 详情(内联截断) */
.log-detail-inline {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 尾部 */
.log-tail {
  display: flex;
  align-items: center;
  gap: 6px;
  justify-content: flex-end;
  flex-shrink: 0;
}
.log-id {
  font-size: 10px;
  color: var(--text-tertiary);
  letter-spacing: 0.04em;
  font-family: 'JetBrains Mono', monospace;
  opacity: 0.7;
}

/* 行选择框 */
.cell-check {
  background: none;
  border: none;
  padding: 0;
  padding-top: 8px;
  cursor: pointer;
  display: flex;
  align-items: flex-start;
  justify-content: center;
}
.checkbox {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1.5px solid var(--glass-border);
  background: var(--glass-light);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  color: transparent;
}
.checkbox.on {
  background: rgba(132, 204, 22, 0.18);
  border-color: rgba(132, 204, 22, 0.30);
  color: var(--mint);
}

/* 图标按钮 */
.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
}
.icon-btn:hover,
.icon-btn.active {
  border-color: var(--mint);
  color: var(--mint);
}
.icon-btn.danger:hover {
  border-color: var(--color-danger);
  color: var(--color-danger);
}

.log-loading { display: flex; flex-direction: column; gap: 6px; padding: 0 12px; }
.log-empty { padding: 40px 0; }

/* ===== 详情展开 ===== */
.log-detail {
  margin: 0 14px 8px;
  padding: 12px 16px;
  background: color-mix(in srgb, var(--mint) 5%, transparent);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--mint);
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}
.detail-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 10px;
  background: var(--glass-light);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}
.detail-key {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-family: 'JetBrains Mono', monospace;
}
.detail-val {
  font-size: 12px;
  color: var(--text-primary);
  word-break: break-all;
  font-family: 'JetBrains Mono', monospace;
}
.detail-enter-active,
.detail-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.detail-enter-from,
.detail-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
.detail-enter-to,
.detail-leave-from {
  opacity: 1;
  max-height: 400px;
}

/* ===== 分页 ===== */
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 1rem;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.page-btn,
.page-num {
  min-width: 32px;
  height: 32px;
  padding: 0 8px;
  border-radius: var(--radius-sm);
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
  transition: all 0.15s ease;
}
.page-btn:hover:not(:disabled),
.page-num:hover:not(.ellipsis):not(.active) {
  border-color: var(--mint);
  color: var(--mint);
}
.page-btn:disabled,
.page-num.ellipsis {
  opacity: 0.4;
  cursor: not-allowed;
}
.page-num.active {
  background: rgba(132, 204, 22, 0.14);
  color: var(--mint);
  border-color: rgba(132, 204, 22, 0.20);
  box-shadow: inset 0 0 0 1px rgba(132, 204, 22, 0.20);
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

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .log-row {
    grid-template-columns: 32px 120px 100px 1fr 80px;
  }
  .log-detail-inline { display: none; }
}
@media (max-width: 640px) {
  .log-row {
    grid-template-columns: 28px 1fr 70px;
    gap: 8px;
    padding: 10px 8px;
  }
  .log-time { font-size: 10px; }
  .log-badge { font-size: 10px; padding: 2px 8px; }
  .log-user { display: none; }
  .log-detail-inline { display: none; }
  .log-detail {
    margin: 0 8px 8px;
    padding: 10px 12px;
  }
}


</style>
