<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { listGateways, listAllGateways, approve, reject, bindGateway, unbind } from '@/api/gateway'
import { listDevices, bindDevice, deviceStream, sendCmd } from '@/api/device'
import { getSocket } from '@/ws/socket'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassTabs from '@/components/glass/GlassTabs.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import GlassDrawer from '@/components/glass/GlassDrawer.vue'
import GlassInput from '@/components/glass/GlassInput.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import DecryptedText from '@/components/vuebits/DecryptedText.vue'
import AnimatedContent from '@/components/vuebits/AnimatedContent.vue'
import FadeContent from '@/components/vuebits/FadeContent.vue'
import Icon from '@/components/icons/Icon.vue'

const route = useRoute()
const ui = useUiStore()

const loading = ref(true)
const gateways = ref([])              // 我的网关列表 [{ ...gw, devices: [] }]
const allGateways = ref([])            // 全部网关(寻找网关抽屉)
const pendingList = ref([])            // 待审批列表
const searchLoading = ref(false)
const tab = ref(0)                     // 0=我的网关 1=待审批
const activeGwId = ref(null)           // 当前选中的网关 id

// 抽屉/弹窗状态
const searchDrawer = ref(false)
const streamDrawer = reactive({ visible: false, device: null, records: [], loading: false })
const nameDialog = reactive({ visible: false, did: null, name: '', loading: false })
const bindDialog = reactive({ visible: false, gw: null, name: '', loading: false })
const confirmDialog = reactive({ visible: false, title: '', message: '', action: null, loading: false })

const STATUS_META = {
  pending:   { label: '待审批', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  approved:  { label: '已审批', color: '#84cc16', bg: 'rgba(132,204,22,0.12)' },
  online:    { label: '在线',   color: '#34d399', bg: 'rgba(52,211,153,0.12)' },
  offline:   { label: '离线',   color: '#6b7280', bg: 'rgba(107,114,128,0.12)' },
  rejected:  { label: '已拒绝', color: '#f87171', bg: 'rgba(248,113,113,0.12)' }
}

const METRIC_LABELS = { temperature: '温度', humidity: '湿度', light: '光照' }

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

function typeLabel(t) {
  const arr = parseType(t)
  return arr.map((k) => METRIC_LABELS[k] || k).join(' / ')
}

function isDeviceActive(s) { return s === 'active' || s === 1 || s === '1' }
function isLedOn(s) { return s === true || s === 1 || s === '1' || s === 'true' }

const activeGw = computed(() => gateways.value.find((g) => g.id === activeGwId.value) || null)
const pendingCount = computed(() => pendingList.value.length)

// ============ 加载 ============
async function loadGateways(silent = false) {
  if (!silent) loading.value = true
  try {
    const gws = await listGateways()
    const list = await Promise.all(
      gws.map(async (gw) => {
        const devs = await listDevices(gw.id).catch(() => [])
        return { ...gw, devices: devs || [] }
      })
    )
    gateways.value = list
    if (!activeGwId.value && list.length) activeGwId.value = list[0].id
    else if (activeGwId.value && !list.find((g) => g.id === activeGwId.value)) {
      activeGwId.value = list.length ? list[0].id : null
    }
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadPending() {
  try {
    const all = await listAllGateways()
    pendingList.value = (all || []).filter((g) => g.status === 'pending')
  } catch (e) { /* 忽略 */ }
}

async function refresh() {
  await Promise.all([loadGateways(true), loadPending()])
  ui.pushToast({ type: 'info', title: '已刷新' })
}

// ============ 寻找网关 ============
async function openSearch() {
  searchDrawer.value = true
  searchLoading.value = true
  try {
    allGateways.value = await listAllGateways()
  } finally {
    searchLoading.value = false
  }
}

async function doApprove(gw) {
  try {
    await approve(gw.gw_uuid)
    ui.pushToast({ type: 'success', title: '网关审批通过' })
    await openSearch()
    await loadPending()
  } catch (e) { /* handled */ }
}

function askReject(gw) {
  confirmDialog.title = '拒绝网关接入'
  confirmDialog.message = `确定拒绝网关「${gw.hostname || gw.gw_uuid}」接入?此操作不可撤销。`
  confirmDialog.action = async () => {
    await reject(gw.gw_uuid)
    ui.pushToast({ type: 'success', title: '已拒绝' })
    await openSearch()
    await loadPending()
  }
  confirmDialog.visible = true
}

function openBind(gw) {
  bindDialog.gw = gw
  bindDialog.name = gw.hostname || ''
  bindDialog.visible = true
}

async function doBind() {
  bindDialog.loading = true
  try {
    await bindGateway(bindDialog.gw.gw_uuid, bindDialog.name)
    ui.pushToast({ type: 'success', title: '绑定成功' })
    bindDialog.visible = false
    await openSearch()
    await loadGateways(true)
  } catch (e) { /* handled */ } finally {
    bindDialog.loading = false
  }
}

function askUnbind(gw) {
  confirmDialog.title = '解绑网关'
  confirmDialog.message = `解绑网关「${gw.name || gw.gw_uuid}」?解绑后该网关下设备将不再向您推送数据。`
  confirmDialog.action = async () => {
    await unbind(gw.id)
    ui.pushToast({ type: 'success', title: '已解绑' })
    await loadGateways(true)
  }
  confirmDialog.visible = true
}

async function runConfirm() {
  if (!confirmDialog.action) return
  confirmDialog.loading = true
  try {
    await confirmDialog.action()
    confirmDialog.visible = false
  } catch (e) { /* handled */ } finally {
    confirmDialog.loading = false
  }
}

// ============ 设备命名 / 数据流 ============
function openName(dev) {
  nameDialog.did = dev.id
  nameDialog.name = dev.name || ''
  nameDialog.visible = true
}

async function doBindDevice() {
  nameDialog.loading = true
  try {
    await bindDevice(nameDialog.did, { name: nameDialog.name })
    ui.pushToast({ type: 'success', title: '已命名并绑定' })
    nameDialog.visible = false
    await loadGateways(true)
  } catch (e) { /* handled */ } finally {
    nameDialog.loading = false
  }
}

async function openStream(dev) {
  streamDrawer.device = dev
  streamDrawer.visible = true
  streamDrawer.loading = true
  streamDrawer.records = []
  try {
    streamDrawer.records = await deviceStream(dev.id)
  } catch (e) { /* handled */ } finally {
    streamDrawer.loading = false
  }
}

// ============ 控制指令 (LED / STATUS) ============
const pendingCmds = reactive({})
const lastClickTs = reactive({})
const CLICK_DEBOUNCE_MS = 500
const FEEDBACK_TIMEOUT_MS = 3000

function cmdKey(devId, c) { return `${devId}:${c}` }
function isPending(dev, c) { return !!pendingCmds[cmdKey(dev.id, c)] }

async function cmd(dev, c, value) {
  const k = cmdKey(dev.id, c)
  const now = Date.now()
  if (now - (lastClickTs[k] || 0) < CLICK_DEBOUNCE_MS) return
  lastClickTs[k] = now
  if (pendingCmds[k]) return

  const origin = c === 'LED' ? (isLedOn(dev.led_status) ? 1 : 0)
                              : (isDeviceActive(dev.device_status) ? 1 : 0)
  pendingCmds[k] = {
    target: value,
    origin,
    timer: setTimeout(() => {
      if (pendingCmds[k]) {
        delete pendingCmds[k]
        ui.pushToast({ type: 'danger', title: `${c} 指令失败`, message: '设备 3s 内未响应' })
      }
    }, FEEDBACK_TIMEOUT_MS)
  }

  try {
    await sendCmd(dev.id, c, value)
  } catch (e) {
    if (pendingCmds[k]) {
      clearTimeout(pendingCmds[k].timer)
      delete pendingCmds[k]
    }
    ui.pushToast({ type: 'danger', title: `${c} 指令下发失败`, message: e?.message || '网络错误' })
  }
}

function toggleLed(dev) { cmd(dev, 'LED', isLedOn(dev.led_status) ? 0 : 1) }
function toggleStatus(dev) { cmd(dev, 'STATUS', isDeviceActive(dev.device_status) ? 0 : 1) }

function findDevice(devId) {
  for (const gw of gateways.value) {
    if (!gw.devices) continue
    const idx = gw.devices.findIndex((d) => d.id === devId)
    if (idx >= 0) return { list: gw.devices, idx }
  }
  return null
}

function _checkPendingSuccess(devId, field, value) {
  const cmdName = field === 'led_status' ? 'LED' : 'STATUS'
  const k = cmdKey(devId, cmdName)
  const p = pendingCmds[k]
  if (!p) return
  const t = p.target
  const matched =
    value === t ||
    (t === 1 && (value === true || value === 1 || value === '1' || value === 'active')) ||
    (t === 0 && (value === false || value === 0 || value === '0' || value === 'sleep'))
  if (matched) {
    clearTimeout(p.timer)
    delete pendingCmds[k]
    ui.pushToast({ type: 'success', title: `${cmdName} 指令执行成功` })
  }
}

// ============ WebSocket ============
let socket
function onDeviceDiscovered() {
  loadGateways(true)
  loadPending()
}
function onSensorData(p) {
  if (!p || !p.device_id) return
  const found = findDevice(p.device_id)
  if (!found) return
  const dev = found.list[found.idx]
  if ('led_status' in p) {
    dev.led_status = p.led_status
    _checkPendingSuccess(p.device_id, 'led_status', p.led_status)
  }
  if ('device_status' in p) {
    dev.device_status = p.device_status
    _checkPendingSuccess(p.device_id, 'device_status', p.device_status)
  }
}

onMounted(async () => {
  await Promise.all([loadGateways(), loadPending()])
  socket = getSocket()
  socket.off('device_discovered', onDeviceDiscovered)
  socket.on('device_discovered', onDeviceDiscovered)
  socket.off('sensor_data', onSensorData)
  socket.on('sensor_data', onSensorData)

  const hid = route.query.highlight
  if (hid) {
    await nextTick()
    const el = document.getElementById('dev-' + hid)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el.classList.add('dev-highlight')
      setTimeout(() => el.classList.remove('dev-highlight'), 3000)
    }
  }
})

onBeforeUnmount(() => {
  if (socket) {
    socket.off('device_discovered', onDeviceDiscovered)
    socket.off('sensor_data', onSensorData)
  }
  for (const k of Object.keys(pendingCmds)) {
    if (pendingCmds[k]?.timer) clearTimeout(pendingCmds[k].timer)
    delete pendingCmds[k]
  }
})
</script>

<template>
  <div class="devices page-container">
    <PageHeader
      title="设备管理"
      eyebrow="DEVICES"
      :rotating-words="['网关', '节点', '控制指令', '审批']"
    >
      <template #extra>
        <div class="header-actions">
          <button class="glass-btn glass-btn--primary" data-cursor-target @click="openSearch">
            <Icon name="search" :size="14" />
            <span>寻找网关</span>
          </button>
          <button class="glass-btn" data-cursor-target @click="refresh">
            <Icon name="refresh" :size="14" />
            <span>刷新</span>
          </button>
        </div>
      </template>
    </PageHeader>

    <GlassTabs
      v-model="tab"
      :tabs="[
        { name: 'mine', label: `我的网关 · ${gateways.length}` },
        { name: 'pending', label: `待审批 · ${pendingCount}` }
      ]"
    />

    <!-- Tab 1: 我的网关 -->
    <div v-show="tab === 0" class="tab-pane">
      <div v-if="loading" class="loading-grid">
        <div v-for="i in 3" :key="i" class="glass-skeleton" style="height: 120px; border-radius: var(--radius-lg)" />
      </div>

      <div v-else-if="!gateways.length" class="empty-wrap">
        <GlassCard padding="p-8" :hover="false">
          <GlassEmpty
            icon="gateway"
            title="尚未绑定网关"
            description="点击右上「寻找网关」,查看所有可用网关并完成绑定。"
          >
            <template #action>
              <button class="glass-btn glass-btn--primary" data-cursor-target @click="openSearch">
                <Icon name="search" :size="14" /> 寻找网关
              </button>
            </template>
          </GlassEmpty>
        </GlassCard>
      </div>

      <div v-else class="mine-layout">
        <!-- 左栏: 网关列表 -->
        <aside class="gw-list">
          <GlassCard padding="p-4" :hover="false" class="gw-list-card">
            <p class="eyebrow mb-3">GATEWAYS · {{ gateways.length }}</p>
            <button
              v-for="gw in gateways"
              :key="gw.id"
              class="gw-item"
              :class="{ active: gw.id === activeGwId }"
              data-cursor-target
              @click="activeGwId = gw.id"
            >
              <div class="gw-item-mark" :class="{ online: gw.status === 'online' || !gw.status }" />
              <div class="gw-item-body">
                <p class="gw-item-name">{{ gw.name || '未命名网关' }}</p>
                <p class="gw-item-meta">{{ gw.hostname || '—' }} · {{ gw.devices?.length || 0 }} 设备</p>
              </div>
              <Icon name="chevronRight" :size="14" class="gw-item-arrow" />
            </button>
          </GlassCard>
        </aside>

        <!-- 右栏: 当前网关详情 + 设备网格 -->
        <section v-if="activeGw" class="gw-detail">
          <AnimatedContent :distance="40" direction="up" :duration="0.6">
            <GlassCard padding="p-6" class="gw-detail-head">
              <div class="gw-head-top">
                <div class="gw-head-id">
                  <span class="gw-mark-square" />
                  <div class="min-w-0">
                    <h3 class="gw-detail-name">{{ activeGw.name || '未命名网关' }}</h3>
                    <div class="gw-uuid-row">
                      <span class="eyebrow">UUID</span>
                      <DecryptedText :text="activeGw.gw_uuid" class="gw-uuid-value" />
                    </div>
                  </div>
                </div>
                <button class="glass-btn glass-btn-danger" data-cursor-target @click="askUnbind(activeGw)">
                  <Icon name="unlink" :size="13" />
                  <span>解绑</span>
                </button>
              </div>

              <div class="gw-meta-row">
                <div class="gw-meta-pill">
                  <span class="eyebrow">主机</span>
                  <span class="gw-meta-value">{{ activeGw.hostname || '—' }}</span>
                </div>
                <div class="gw-meta-pill">
                  <span class="eyebrow">IP</span>
                  <span class="gw-meta-value data-value">{{ activeGw.ip || '—' }}</span>
                </div>
                <div class="gw-meta-pill">
                  <span class="eyebrow">设备</span>
                  <span class="gw-meta-value">{{ activeGw.devices?.length || 0 }} 台</span>
                </div>
                <div class="gw-meta-pill">
                  <span class="eyebrow">状态</span>
                  <span class="gw-meta-value" :style="{ color: STATUS_META[activeGw.status]?.color || STATUS_META.online.color }">
                    {{ STATUS_META[activeGw.status]?.label || '在线' }}
                  </span>
                </div>
              </div>
            </GlassCard>
          </AnimatedContent>

          <!-- 设备网格 -->
          <div class="dev-section">
            <div class="dev-section-head">
              <p class="eyebrow">DEVICES</p>
              <h4 class="dev-section-title">终端设备 · {{ activeGw.devices?.length || 0 }}</h4>
            </div>

            <div v-if="!activeGw.devices?.length" class="dev-empty">
              <GlassCard padding="p-6" :hover="false">
                <p class="text-sm" style="color: var(--text-tertiary)">该网关下暂无设备,等待设备注册接入…</p>
              </GlassCard>
            </div>

            <AnimatedContent v-else :distance="60" direction="up" :delay="0.1">
              <div class="dev-grid">
                <FadeContent
                  v-for="dev in activeGw.devices"
                  :key="dev.id"
                  :distance="20"
                  :delay="0.04"
                >
                  <GlassCard
                    :id="'dev-' + dev.id"
                    padding="p-5"
                    class="dev-card sheen-on-hover"
                  >
                    <div class="dev-card-head">
                      <div class="dev-title" data-cursor-target @click="openStream(dev)">
                        <span class="dev-name">{{ dev.name || dev.mac || '未命名设备' }}</span>
                        <span class="dev-bound" :class="{ bound: dev.bound }">
                          {{ dev.bound ? '已绑定' : '未绑定' }}
                        </span>
                      </div>
                      <span class="tag-pill">{{ typeLabel(dev.type) }}</span>
                    </div>

                    <div class="dev-mac-row">
                      <span class="eyebrow">MAC</span>
                      <DecryptedText :text="dev.mac || '—'" class="dev-mac-value" :speed="40" />
                    </div>

                    <div class="dev-actions">
                      <button class="glass-btn glass-btn-sm" data-cursor-target @click="openName(dev)">
                        <Icon name="edit" :size="12" /> 命名
                      </button>
                      <button class="glass-btn glass-btn-sm" data-cursor-target @click="openStream(dev)">
                        <Icon name="activity" :size="12" /> 数据流
                      </button>
                    </div>

                    <div class="dev-ctrl">
                      <button
                        class="ctrl-btn led"
                        :class="{ on: isLedOn(dev.led_status), pending: isPending(dev, 'LED') }"
                        :disabled="isPending(dev, 'LED')"
                        data-cursor-target
                        @click="toggleLed(dev)"
                      >
                        <span class="ctrl-dot led-dot" />
                        <span v-if="isPending(dev, 'LED')" class="ctrl-text">···</span>
                        <span v-else>LED</span>
                      </button>
                      <button
                        class="ctrl-btn st"
                        :class="{ on: isDeviceActive(dev.device_status), pending: isPending(dev, 'STATUS') }"
                        :disabled="isPending(dev, 'STATUS')"
                        data-cursor-target
                        @click="toggleStatus(dev)"
                      >
                        <span class="ctrl-dot st-dot" />
                        <span v-if="isPending(dev, 'STATUS')" class="ctrl-text">···</span>
                        <span v-else>{{ isDeviceActive(dev.device_status) ? '运行' : '休眠' }}</span>
                      </button>
                    </div>
                  </GlassCard>
                </FadeContent>
              </div>
            </AnimatedContent>
          </div>
        </section>
      </div>
    </div>

    <!-- Tab 2: 待审批 -->
    <div v-show="tab === 1" class="tab-pane">
      <div v-if="!pendingList.length" class="empty-wrap">
        <GlassCard padding="p-8" :hover="false">
          <GlassEmpty
            icon="shield"
            title="暂无待审批网关"
            description="新接入的网关将在此处显示,您可以审批或拒绝。"
          />
        </GlassCard>
      </div>

      <div v-else class="pending-list">
        <FadeContent
          v-for="gw in pendingList"
          :key="gw.id"
          :distance="24"
          :delay="0.05"
        >
          <GlassCard padding="p-5" class="pending-card">
            <div class="pending-head">
              <div class="min-w-0">
                <div class="pending-host">{{ gw.hostname || '未知主机' }}</div>
                <div class="pending-uuid-row">
                  <span class="eyebrow">UUID</span>
                  <DecryptedText :text="gw.gw_uuid" class="pending-uuid" />
                </div>
              </div>
              <span class="pending-tag" :style="{ background: STATUS_META.pending.bg, color: STATUS_META.pending.color }">
                {{ STATUS_META.pending.label }}
              </span>
            </div>

            <div class="pending-meta">
              <div class="pending-meta-item">
                <span class="eyebrow">IP</span>
                <span class="data-value">{{ gw.ip || '—' }}</span>
              </div>
              <div v-if="gw.bind_name" class="pending-meta-item">
                <span class="eyebrow">名称</span>
                <span>{{ gw.bind_name }}</span>
              </div>
            </div>

            <div class="pending-actions">
              <button class="glass-btn glass-btn--primary glass-btn-sm" data-cursor-target @click="doApprove(gw)">
                <Icon name="check" :size="13" /> 审批通过
              </button>
              <button class="glass-btn glass-btn-danger glass-btn-sm" data-cursor-target @click="askReject(gw)">
                <Icon name="close" :size="13" /> 拒绝
              </button>
              <button
                v-if="gw.status === 'approved'"
                class="glass-btn glass-btn-sm"
                data-cursor-target
                @click="openBind(gw)"
              >
                <Icon name="link" :size="13" /> 绑定
              </button>
            </div>
          </GlassCard>
        </FadeContent>
      </div>
    </div>

    <!-- 寻找网关抽屉 -->
    <GlassDrawer
      v-model="searchDrawer"
      title="寻找网关"
      subtitle="DISCOVER · 所有可用网关"
      side="right"
      width="520px"
    >
      <div v-if="searchLoading" class="drawer-loading">
        <div v-for="i in 3" :key="i" class="glass-skeleton" style="height: 130px; border-radius: var(--radius-lg); margin-bottom: 12px" />
      </div>

      <div v-else-if="!allGateways.length" class="drawer-empty">
        <GlassEmpty
          icon="wifi"
          title="未发现可用网关"
          description="请确保本地网关已启动并注册到 EMQX。"
          :decorative="false"
        />
      </div>

      <div v-else class="search-list">
        <FadeContent
          v-for="gw in allGateways"
          :key="gw.id"
          :distance="20"
          :delay="0.03"
        >
          <GlassCard padding="p-5" class="search-card" :class="{ bound: gw.bound }">
            <div class="search-head">
              <span class="search-host">{{ gw.hostname || '未知主机' }}</span>
              <div class="search-badges">
                <span
                  class="search-tag"
                  :style="{ background: (STATUS_META[gw.status] || STATUS_META.offline).bg, color: (STATUS_META[gw.status] || STATUS_META.offline).color }"
                >
                  {{ (STATUS_META[gw.status] || STATUS_META.offline).label }}
                </span>
                <span v-if="gw.bound" class="search-tag search-tag-bound">已绑定</span>
              </div>
            </div>

            <div class="search-uuid-row">
              <span class="eyebrow">UUID</span>
              <DecryptedText :text="gw.gw_uuid" class="search-uuid" :speed="40" />
            </div>
            <div class="search-row">
              <span class="eyebrow">IP</span>
              <span class="data-value">{{ gw.ip || '—' }}</span>
            </div>
            <div v-if="gw.bind_name" class="search-row">
              <span class="eyebrow">名称</span>
              <span>{{ gw.bind_name }}</span>
            </div>

            <div class="search-actions">
              <template v-if="gw.status === 'pending'">
                <button class="glass-btn glass-btn--primary glass-btn-sm" data-cursor-target @click="doApprove(gw)">
                  <Icon name="check" :size="13" /> 审批通过
                </button>
                <button class="glass-btn glass-btn-danger glass-btn-sm" data-cursor-target @click="askReject(gw)">
                  <Icon name="close" :size="13" /> 拒绝
                </button>
              </template>
              <template v-else-if="(gw.status === 'approved' || gw.status === 'online') && !gw.bound">
                <button class="glass-btn glass-btn--primary glass-btn-sm" data-cursor-target @click="openBind(gw)">
                  <Icon name="link" :size="13" /> 绑定此网关
                </button>
              </template>
              <template v-else-if="gw.bound">
                <span class="search-hint">您已绑定此网关,如需解绑请返回主页面操作</span>
              </template>
              <template v-else>
                <span class="search-hint">此网关暂不可绑定</span>
              </template>
            </div>
          </GlassCard>
        </FadeContent>
      </div>
    </GlassDrawer>

    <!-- 数据流抽屉 -->
    <GlassDrawer
      :model-value="streamDrawer.visible"
      @update:model-value="streamDrawer.visible = $event"
      :title="streamDrawer.device?.name || streamDrawer.device?.mac || '设备数据流'"
      subtitle="STREAM · 最近 5 条数据"
      side="right"
      width="460px"
    >
      <div v-if="streamDrawer.loading" class="drawer-loading">
        <div v-for="i in 4" :key="i" class="glass-skeleton" style="height: 60px; border-radius: 8px; margin-bottom: 8px" />
      </div>
      <div v-else-if="!streamDrawer.records.length" class="drawer-empty">
        <GlassEmpty icon="activity" title="暂无历史数据" :decorative="false" />
      </div>
      <div v-else class="stream-list">
        <div v-for="(r, i) in streamDrawer.records" :key="i" class="stream-row">
          <div class="stream-time data-value">{{ r.recorded_at }}</div>
          <div class="stream-reads">
            <span v-if="r.temperature !== null && r.temperature !== undefined" class="read-pill read-temp">
              T<b>{{ r.temperature }}</b>°C
            </span>
            <span v-if="r.humidity !== null && r.humidity !== undefined" class="read-pill read-hum">
              H<b>{{ r.humidity }}</b>%
            </span>
            <span v-if="r.light !== null && r.light !== undefined" class="read-pill read-light">
              L<b>{{ r.light }}</b>lux
            </span>
          </div>
        </div>
      </div>
    </GlassDrawer>

    <!-- 绑定网关弹窗 -->
    <GlassModal v-model="bindDialog.visible" title="绑定网关" size="sm">
      <p class="modal-desc">为网关「{{ bindDialog.gw?.hostname || bindDialog.gw?.gw_uuid }}」设置一个自定义名称(可选),确认后即可绑定。</p>
      <GlassInput
        v-model="bindDialog.name"
        placeholder="如:客厅网关"
        maxlength="32"
      />
      <div class="modal-footer">
        <button class="glass-btn" data-cursor-target @click="bindDialog.visible = false">取消</button>
        <button class="glass-btn glass-btn--primary" data-cursor-target :disabled="bindDialog.loading" @click="doBind">
          <Icon v-if="bindDialog.loading" name="refresh" :size="13" class="spin" />
          <Icon v-else name="link" :size="13" />
          <span>确认绑定</span>
        </button>
      </div>
    </GlassModal>

    <!-- 命名设备弹窗 -->
    <GlassModal v-model="nameDialog.visible" title="命名并绑定设备" size="sm">
      <p class="modal-desc">为设备起一个易记的名字,便于后续管理与查找。</p>
      <GlassInput
        v-model="nameDialog.name"
        placeholder="如:阳台温湿度节点"
        maxlength="32"
      />
      <div class="modal-footer">
        <button class="glass-btn" data-cursor-target @click="nameDialog.visible = false">取消</button>
        <button class="glass-btn glass-btn--primary" data-cursor-target :disabled="nameDialog.loading" @click="doBindDevice">
          <Icon v-if="nameDialog.loading" name="refresh" :size="13" class="spin" />
          <Icon v-else name="check" :size="13" />
          <span>绑定</span>
        </button>
      </div>
    </GlassModal>

    <!-- 确认弹窗 (拒绝/解绑) -->
    <GlassModal v-model="confirmDialog.visible" :title="confirmDialog.title" size="sm">
      <p class="modal-desc">{{ confirmDialog.message }}</p>
      <div class="modal-footer">
        <button class="glass-btn" data-cursor-target @click="confirmDialog.visible = false">取消</button>
        <button class="glass-btn glass-btn-danger" data-cursor-target :disabled="confirmDialog.loading" @click="runConfirm">
          <Icon v-if="confirmDialog.loading" name="refresh" :size="13" class="spin" />
          <Icon v-else name="warning" :size="13" />
          <span>确认</span>
        </button>
      </div>
    </GlassModal>
  </div>
</template>

<style scoped>
.devices { }

.header-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.tab-pane { margin-top: 1rem; }

.loading-grid {
  display: grid;
  gap: 12px;
}

.empty-wrap {
  max-width: 480px;
  margin: 0 auto;
}

/* ===== 我的网关 布局 ===== */
.mine-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 1.25rem;
  align-items: start;
}
@media (max-width: 1024px) {
  .mine-layout {
    grid-template-columns: 1fr;
  }
}

/* —— 左栏 网关列表 —— */
.gw-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gw-list-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.gw-item {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--glass-light);
  border: 1px solid transparent;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s ease;
  color: var(--text-secondary);
}
.gw-item:hover {
  background: var(--glass-medium);
  border-color: var(--glass-border);
}
.gw-item.active {
  background: rgba(132, 204, 22, 0.08);
  border-color: rgba(132, 204, 22, 0.3);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 4px 16px rgba(52, 211, 153, 0.08);
}
.gw-item-mark {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.12);
  flex-shrink: 0;
  transition: all 0.3s ease;
}
.gw-item-mark.online {
  background: var(--mint);
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.15), 0 0 8px rgba(52, 211, 153, 0.4);
}
.gw-item-body {
  flex: 1;
  min-width: 0;
}
.gw-item-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gw-item-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.02em;
}
.gw-item-arrow {
  color: var(--text-tertiary);
  transition: transform 0.2s ease;
}
.gw-item.active .gw-item-arrow {
  color: var(--mint);
  transform: translateX(2px);
}

/* —— 右栏 网关详情 —— */
.gw-detail {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.gw-detail-head {
  position: relative;
}
.gw-detail-head::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(132, 204, 22, 0.4), rgba(20, 184, 166, 0.4), transparent);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}
.gw-head-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.gw-head-id {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  min-width: 0;
  flex: 1;
}
.gw-mark-square {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(135deg, var(--sage), var(--teal));
  box-shadow: 0 0 0 4px rgba(132, 204, 22, 0.12), 0 0 12px rgba(52, 211, 153, 0.3);
  flex-shrink: 0;
  margin-top: 6px;
}
.gw-detail-name {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 700;
  font-size: 22px;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  line-height: 1.2;
  margin-bottom: 6px;
  word-break: break-all;
}
.gw-uuid-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.gw-uuid-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--mint);
  letter-spacing: 0.04em;
  word-break: break-all;
}

.gw-meta-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding-top: 16px;
  border-top: 1px solid var(--glass-border);
}
.gw-meta-pill {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.gw-meta-value {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
@media (max-width: 1280px) {
  .gw-meta-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* —— 设备网格 —— */
.dev-section-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 1rem;
}
.dev-section-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.dev-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1rem;
}
@media (max-width: 600px) {
  .dev-grid {
    grid-template-columns: 1fr;
  }
}

.dev-card {
  height: 100%;
  position: relative;
}
.dev-card.dev-highlight {
  border-color: var(--mint) !important;
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.18), 0 0 24px rgba(52, 211, 153, 0.25) !important;
  animation: hl-pulse 0.7s ease-out 3;
}
@keyframes hl-pulse {
  0%, 100% { box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.18), 0 0 24px rgba(52, 211, 153, 0.25); }
  50%      { box-shadow: 0 0 0 8px rgba(52, 211, 153, 0.25), 0 0 36px rgba(52, 211, 153, 0.4); }
}

.dev-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}
.dev-title {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.dev-title:hover .dev-name { color: var(--mint); }
.dev-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: color 0.2s ease;
}
.dev-bound {
  font-size: 9px;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: rgba(245, 158, 11, 0.12);
  color: var(--amber);
  border: 1px solid rgba(245, 158, 11, 0.2);
  flex-shrink: 0;
}
.dev-bound.bound {
  background: rgba(52, 211, 153, 0.12);
  color: var(--mint);
  border-color: rgba(52, 211, 153, 0.3);
}

.dev-mac-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}
.dev-mac-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}

.dev-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 12px;
}
.glass-btn-sm {
  padding: 4px 10px;
  font-size: 11px;
  border-radius: 999px;
}

.dev-ctrl {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--glass-border);
}
.ctrl-btn {
  flex: 1;
  border: 1px solid var(--glass-border);
  background: var(--glass-light);
  border-radius: var(--radius-sm);
  padding: 8px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: 'DM Sans', sans-serif;
  font-weight: 500;
}
.ctrl-btn:hover:not(.pending):not(:disabled) {
  border-color: rgba(132, 204, 22, 0.3);
  color: var(--mint);
  background: var(--glass-medium);
}
.ctrl-btn.pending {
  cursor: progress;
  opacity: 0.7;
  position: relative;
}
.ctrl-btn.pending::after {
  content: '';
  position: absolute;
  top: 50%;
  right: 8px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  border: 1.5px solid var(--text-tertiary);
  border-top-color: transparent;
  transform: translateY(-50%);
  animation: ctrl-spin 0.8s linear infinite;
}
@keyframes ctrl-spin {
  to { transform: translateY(-50%) rotate(360deg); }
}
.ctrl-btn.pending .ctrl-text {
  letter-spacing: 2px;
  font-family: 'JetBrains Mono', monospace;
}
.ctrl-btn:disabled { cursor: progress; }

.ctrl-btn.led.on {
  background: rgba(132, 204, 22, 0.14);
  color: var(--mint);
  border-color: rgba(132, 204, 22, 0.20);
  box-shadow: inset 0 0 0 1px rgba(132, 204, 22, 0.20);
}
.ctrl-btn.st.on {
  background: rgba(132, 204, 22, 0.14);
  color: var(--mint);
  border-color: rgba(132, 204, 22, 0.20);
  box-shadow: inset 0 0 0 1px rgba(132, 204, 22, 0.20);
}
.ctrl-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.2s ease;
}
.ctrl-btn.led.on .led-dot {
  background: #fff;
  box-shadow: 0 0 6px rgba(255, 255, 255, 0.9), 0 0 12px rgba(52, 211, 153, 0.6);
}
.ctrl-btn.st.on .st-dot {
  background: #fff;
  box-shadow: 0 0 6px rgba(255, 255, 255, 0.9), 0 0 12px rgba(52, 211, 153, 0.6);
}

/* ===== 待审批 列表 ===== */
.pending-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 1rem;
}
.pending-card { height: 100%; }
.pending-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.pending-host {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 18px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  margin-bottom: 6px;
}
.pending-uuid-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pending-uuid {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
  word-break: break-all;
}
.pending-tag {
  font-size: 10px;
  padding: 3px 10px;
  border-radius: 999px;
  letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace;
  flex-shrink: 0;
}
.pending-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.pending-meta-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}
.pending-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 12px;
  border-top: 1px dashed var(--glass-border);
}

/* ===== 抽屉 ===== */
.drawer-loading { padding: 4px 0; }
.drawer-empty { padding: 40px 0; }

.search-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.search-card.bound {
  border-color: rgba(52, 211, 153, 0.3);
}
.search-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.search-host {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
}
.search-badges {
  display: flex;
  gap: 6px;
  align-items: center;
}
.search-tag {
  font-size: 9px;
  padding: 2px 10px;
  border-radius: 999px;
  letter-spacing: 0.08em;
  font-family: 'JetBrains Mono', monospace;
}
.search-tag-bound {
  background: rgba(52, 211, 153, 0.12) !important;
  color: var(--mint) !important;
}
.search-uuid-row,
.search-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--text-tertiary);
}
.search-uuid {
  font-family: 'JetBrains Mono', monospace;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
  word-break: break-all;
}
.search-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--glass-border);
}
.search-hint {
  font-size: 12px;
  color: var(--text-tertiary);
}

/* ===== 数据流 ===== */
.stream-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stream-row {
  padding: 14px 0;
  border-bottom: 1px dashed var(--glass-border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.stream-row:last-child { border-bottom: none; }
.stream-time {
  font-size: 11px;
  color: var(--text-tertiary);
}
.stream-reads {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.read-pill {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 999px;
  font-family: 'JetBrains Mono', monospace;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.read-pill b {
  font-weight: 600;
  margin-left: 2px;
}
.read-temp {
  background: rgba(245, 158, 11, 0.1);
  color: var(--amber);
}
.read-hum {
  background: rgba(20, 184, 166, 0.1);
  color: var(--teal);
}
.read-light {
  background: rgba(163, 230, 53, 0.1);
  color: var(--sage-soft);
}

/* ===== 弹窗 ===== */
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

.spin {
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}


</style>
