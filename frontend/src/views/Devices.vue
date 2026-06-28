<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listGateways, listAllGateways, approve, reject, bindGateway, unbind } from '@/api/gateway'
import { listDevices, bindDevice, deviceStream, sendCmd } from '@/api/device'
import { getSocket } from '@/ws/socket'

const loading = ref(true)
const gateways = ref([])
const allGateways = ref([])          // 全部网关列表(含绑定状态)
const searchDrawer = ref(false)      // 寻找网关抽屉
const searchLoading = ref(false)

// 设备命名弹窗
const nameDialog = reactive({ visible: false, did: null, name: '', loading: false })
// 绑定网关弹窗(审批通过后绑定)
const bindDialog = reactive({ visible: false, gw: null, name: '', loading: false })
// 数据流抽屉
const streamDrawer = reactive({ visible: false, device: null, records: [], loading: false })

const STATUS_LABEL = {
  pending: '待审',
  approved: '已审批',
  online: '在线',
  offline: '离线',
  rejected: '已拒绝',
}
const STATUS_COLOR = {
  pending: 'var(--amber)',
  approved: 'var(--sage)',
  online: 'var(--sage)',
  offline: 'var(--ink-4)',
  rejected: 'var(--danger, #e36b8b)',
}

async function loadGateways() {
  loading.value = true
  try {
    const gws = await listGateways()
    gateways.value = await Promise.all(
      gws.map(async (gw) => {
        const devs = await listDevices(gw.id).catch(() => [])
        return { ...gw, devices: devs }
      })
    )
  } finally {
    loading.value = false
  }
}

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
    ElMessage.success('网关审批通过')
    await openSearch()  // 刷新全部列表
  } catch (e) { /* handled by interceptor */ }
}

async function doReject(gw) {
  await ElMessageBox.confirm(`拒绝网关 ${gw.hostname || gw.gw_uuid} 接入?`, '拒绝', {
    type: 'warning'
  }).catch(() => 'cancel').then(async (v) => {
    if (v === 'cancel') return
    await reject(gw.gw_uuid)
    ElMessage.success('已拒绝')
    await openSearch()
  })
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
    ElMessage.success('绑定成功')
    bindDialog.visible = false
    await openSearch()
    await loadGateways()
  } catch (e) { /* handled */ } finally {
    bindDialog.loading = false
  }
}

async function doUnbind(gw) {
  await ElMessageBox.confirm(`解绑网关「${gw.name || gw.gw_uuid}」?`, '解绑', {
    type: 'warning'
  }).catch(() => 'cancel').then(async (v) => {
    if (v === 'cancel') return
    await unbind(gw.id)
    ElMessage.success('已解绑')
    await loadGateways()
  })
}

function openName(dev) {
  nameDialog.did = dev.id
  nameDialog.name = dev.name || ''
  nameDialog.visible = true
}

async function doBindDevice() {
  nameDialog.loading = true
  try {
    await bindDevice(nameDialog.did, { name: nameDialog.name })
    ElMessage.success('已命名并绑定')
    nameDialog.visible = false
    await loadGateways()
  } catch (e) {
  } finally {
    nameDialog.loading = false
  }
}

async function openStream(dev) {
  streamDrawer.device = dev
  streamDrawer.visible = true
  streamDrawer.loading = true
  try {
    streamDrawer.records = await deviceStream(dev.id)
  } finally {
    streamDrawer.loading = false
  }
}

// ============ 状态判断(与 Home.vue 保持一致)============
const METRIC_LABELS = { temperature: '温度', humidity: '湿度', light: '光照' }
function typeLabel(typeArr) {
  if (!Array.isArray(typeArr) || !typeArr.length) return null
  return typeArr.map((k) => METRIC_LABELS[k] || k).join('/')
}
function isDeviceActive(status) {
  return status === 'active' || status === 1 || status === '1'
}
function isLedOn(status) {
  return status === true || status === 1 || status === '1' || status === 'true'
}

// ============ 控制指令 ============
const pendingCmds = reactive({})
const lastClickTs = reactive({})
const CLICK_DEBOUNCE_MS = 500
const FEEDBACK_TIMEOUT_MS = 3000

function _pendingKey(devId, cmd) {
  return `${devId}:${cmd}`
}

function isPending(dev, cmd) {
  return !!pendingCmds[_pendingKey(dev.id, cmd)]
}

async function cmd(dev, c, value) {
  const clickKey = _pendingKey(dev.id, c)
  const now = Date.now()
  if (now - (lastClickTs[clickKey] || 0) < CLICK_DEBOUNCE_MS) return
  lastClickTs[clickKey] = now
  if (pendingCmds[clickKey]) return

  const origin = c === 'LED' ? (isLedOn(dev.led_status) ? 1 : 0)
                              : (isDeviceActive(dev.device_status) ? 1 : 0)
  pendingCmds[clickKey] = {
    target: value,
    origin,
    timer: setTimeout(() => {
      if (pendingCmds[clickKey]) {
        delete pendingCmds[clickKey]
        ElMessage.error(`${c} 指令失败:设备 3s 内未响应`)
      }
    }, FEEDBACK_TIMEOUT_MS)
  }

  try {
    await sendCmd(dev.id, c, value)
  } catch (e) {
    if (pendingCmds[clickKey]) {
      clearTimeout(pendingCmds[clickKey].timer)
      delete pendingCmds[clickKey]
    }
    ElMessage.error(`${c} 指令下发失败: ${e?.message || '网络错误'}`)
  }
}

async function toggleLed(dev) {
  const next = isLedOn(dev.led_status) ? 0 : 1
  await cmd(dev, 'LED', next)
}
async function toggleStatus(dev) {
  const next = isDeviceActive(dev.device_status) ? 0 : 1
  await cmd(dev, 'STATUS', next)
}

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
  const key = _pendingKey(devId, cmdName)
  const p = pendingCmds[key]
  if (!p) return
  const v = value
  const t = p.target
  const matched =
    v === t ||
    (t === 1 && (v === true || v === 1 || v === '1' || v === 'active')) ||
    (t === 0 && (v === false || v === 0 || v === '0' || v === 'sleep'))
  if (matched) {
    clearTimeout(p.timer)
    delete pendingCmds[key]
    ElMessage.success(`${cmdName} 指令执行成功`)
  }
}

function onSocket() {
  const s = getSocket()
  s.off('device_discovered').on('device_discovered', () => loadGateways())
  s.off('sensor_data').on('sensor_data', (p) => {
    if (!p.device_id) return
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
  })
}

function offSocket() {
  const s = getSocket()
  s.off('device_discovered')
  s.off('sensor_data')
}

onMounted(async () => {
  await loadGateways()
  onSocket()
  const route = useRoute()
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
  offSocket()
  for (const key of Object.keys(pendingCmds)) {
    if (pendingCmds[key]?.timer) clearTimeout(pendingCmds[key].timer)
    delete pendingCmds[key]
  }
})
</script>

<template>
  <div class="devices">
    <!-- 操作条 -->
    <div class="bar rise rise-1">
      <div class="bar-left">
        <h2 class="bar-title display">设备管理</h2>
        <span class="bar-sub muted">网关 · 节点 · 控制指令</span>
      </div>
      <div class="bar-right">
        <el-button type="primary" @click="openSearch">
          <span class="find-ico">◎</span> 寻找网关
        </el-button>
        <el-button @click="loadGateways">刷新</el-button>
      </div>
    </div>

    <!-- 网关列表 -->
    <div v-loading="loading">
      <section
        v-for="(gw, gi) in gateways"
        :key="gw.id"
        class="gw-section rise"
        :style="{ animationDelay: 0.1 + gi * 0.08 + 's' }"
      >
        <div class="gw-head">
          <div class="gw-id">
            <span class="gw-mark"></span>
            <div>
              <div class="gw-name display">{{ gw.name || '未命名网关' }}</div>
              <div class="gw-uuid mono">{{ gw.gw_uuid }}</div>
            </div>
          </div>
          <div class="gw-meta">
            <span class="gw-pill"><span class="label-eyebrow">主机</span> {{ gw.hostname || '—' }}</span>
            <span class="gw-pill"><span class="label-eyebrow">IP</span> {{ gw.ip || '—' }}</span>
            <span class="gw-pill"><span class="label-eyebrow">设备</span> {{ gw.devices?.length || 0 }}</span>
            <el-button text type="danger" @click="doUnbind(gw)">解绑</el-button>
          </div>
        </div>

        <!-- 设备网格 -->
        <div class="dev-grid" v-if="gw.devices && gw.devices.length">
          <article
            v-for="dev in gw.devices"
            :key="dev.id"
            :id="'dev-' + dev.id"
            class="dev-card"
          >
            <div class="dc-row">
              <div class="dc-title" @click="openStream(dev)">
                <span class="dc-name">{{ dev.name || dev.mac }}</span>
                <span class="dc-bound" :class="{ bound: dev.bound }">{{ dev.bound ? '已绑定' : '未绑定' }}</span>
              </div>
              <span class="dc-type label-eyebrow">{{ typeLabel(dev.type) || '未知' }}</span>
            </div>
            <div class="dc-mac mono">{{ dev.mac }}</div>

            <div class="dc-actions">
              <el-button size="small" @click="openName(dev)">命名 / 绑定</el-button>
              <el-button size="small" @click="openStream(dev)">数据流</el-button>
            </div>
            <div class="dc-ctrl">
              <button
                class="ctrl-btn led"
                :class="{ on: isLedOn(dev.led_status), pending: isPending(dev, 'LED') }"
                :disabled="isPending(dev, 'LED')"
                @click="toggleLed(dev)"
                :title="isLedOn(dev.led_status) ? 'LED 开 · 点击关闭' : 'LED 关 · 点击开启'"
              >
                <span class="ctrl-led"></span>
                <span v-if="isPending(dev, 'LED')" class="ctrl-text">···</span>
                <span v-else>LED</span>
              </button>
              <button
                class="ctrl-btn st"
                :class="{ on: isDeviceActive(dev.device_status), pending: isPending(dev, 'STATUS') }"
                :disabled="isPending(dev, 'STATUS')"
                @click="toggleStatus(dev)"
                :title="isDeviceActive(dev.device_status) ? '运行中 · 点击进入休眠' : '休眠中 · 点击唤醒'"
              >
                <span class="ctrl-dot"></span>
                <span v-if="isPending(dev, 'STATUS')" class="ctrl-text">···</span>
                <span v-else>{{ isDeviceActive(dev.device_status) ? '运行' : '休眠' }}</span>
              </button>
            </div>
          </article>
        </div>
        <el-empty v-else description="该网关下暂无设备" :image-size="60" />
      </section>

      <!-- 空 -->
      <div v-if="!loading && !gateways.length" class="empty">
        <div class="empty-art"></div>
        <h3 class="display">尚未绑定网关</h3>
        <p class="muted">点击右上「寻找网关」,查看所有可用网关并绑定。</p>
        <el-button type="primary" @click="openSearch">寻找网关</el-button>
      </div>
    </div>

    <!-- 寻找网关 抽屉(展示全部网关) -->
    <el-drawer v-model="searchDrawer" title="寻找网关" size="520" direction="rtl">
      <div v-loading="searchLoading" class="search-list">
        <div v-if="!allGateways.length && !searchLoading" class="search-empty muted">
          暂无可用网关。请确保本地网关已启动并注册到 EMQX。
        </div>
        <div v-for="gw in allGateways" :key="gw.id" class="search-card" :class="{ bound: gw.bound }">
          <div class="sc-head">
            <span class="sc-host display">{{ gw.hostname || '未知主机' }}</span>
            <div class="sc-badges">
              <span class="sc-tag" :style="{ background: STATUS_COLOR[gw.status] + '1a', color: STATUS_COLOR[gw.status] }">
                {{ STATUS_LABEL[gw.status] || gw.status }}
              </span>
              <span v-if="gw.bound" class="sc-tag sc-bound-tag">已绑定</span>
            </div>
          </div>
          <div class="sc-row mono">UUID · {{ gw.gw_uuid }}</div>
          <div class="sc-row mono">IP · {{ gw.ip || '—' }}</div>
          <div v-if="gw.bind_name" class="sc-row mono">自定义名称 · {{ gw.bind_name }}</div>
          <div class="sc-actions">
            <!-- pending: 审批 + 拒绝 -->
            <template v-if="gw.status === 'pending'">
              <el-button type="primary" size="small" @click="doApprove(gw)">审批通过</el-button>
              <el-button size="small" @click="doReject(gw)">拒绝</el-button>
            </template>
            <!-- approved/online 且未绑定: 绑定按钮 -->
            <template v-else-if="(gw.status === 'approved' || gw.status === 'online') && !gw.bound">
              <el-button type="primary" size="small" @click="openBind(gw)">绑定此网关</el-button>
            </template>
            <!-- 已绑定: 仅显示状态,无操作 -->
            <template v-else-if="gw.bound">
              <span class="muted" style="font-size:12px">您已绑定此网关,如需解绑请返回主页面操作</span>
            </template>
            <!-- rejected/offline: 无可用操作 -->
            <template v-else>
              <span class="muted" style="font-size:12px">此网关暂不可绑定</span>
            </template>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 绑定网关弹窗 -->
    <el-dialog v-model="bindDialog.visible" title="绑定网关" width="420">
      <p class="muted" style="margin-bottom:14px">为网关设置一个自定义名称(可选),确认后即可绑定。</p>
      <el-input v-model="bindDialog.name" placeholder="如:客厅网关" maxlength="32" show-word-limit />
      <template #footer>
        <el-button @click="bindDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="bindDialog.loading" @click="doBind">确认绑定</el-button>
      </template>
    </el-dialog>

    <!-- 命名弹窗 -->
    <el-dialog v-model="nameDialog.visible" title="命名并绑定设备" width="420">
      <el-input v-model="nameDialog.name" placeholder="为设备起一个名字" maxlength="32" show-word-limit />
      <template #footer>
        <el-button @click="nameDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="nameDialog.loading" @click="doBindDevice">绑定</el-button>
      </template>
    </el-dialog>

    <!-- 数据流抽屉 -->
    <el-drawer v-model="streamDrawer.visible" :title="streamDrawer.device?.name || streamDrawer.device?.mac" size="460" direction="rtl">
      <div v-loading="streamDrawer.loading">
        <div class="stream-head label-eyebrow">最近 5 条数据</div>
        <div class="stream-list">
          <div v-for="(r, i) in streamDrawer.records" :key="i" class="stream-row">
            <div class="sr-time mono">{{ r.recorded_at }}</div>
            <div class="sr-reads mono">
              <span v-if="r.temperature !== null && r.temperature !== undefined">T<b>{{ r.temperature }}</b></span>
              <span v-if="r.humidity !== null && r.humidity !== undefined">H<b>{{ r.humidity }}</b></span>
              <span v-if="r.light !== null && r.light !== undefined">L<b>{{ r.light }}</b></span>
            </div>
          </div>
          <div v-if="!streamDrawer.records.length && !streamDrawer.loading" class="muted" style="padding:20px 0">
            暂无历史数据
          </div>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.devices { max-width: 1240px; }

.bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 28px;
}
.bar-title { font-size: 26px; font-weight: 400; letter-spacing: -0.02em; }
.bar-sub { font-size: 13px; margin-left: 14px; }
.bar-right { display: flex; gap: 10px; }
.find-ico { margin-right: 4px; }

/* 网关区 */
.gw-section {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 26px 28px;
  margin-bottom: 20px;
}
.gw-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 22px;
  gap: 16px;
  flex-wrap: wrap;
}
.gw-id { display: flex; align-items: center; gap: 14px; }
.gw-mark {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--sage);
  box-shadow: 0 0 0 4px var(--sage-soft);
  flex-shrink: 0;
}
.gw-name { font-size: 20px; font-weight: 500; letter-spacing: -0.01em; }
.gw-uuid { font-size: 10px; color: var(--ink-4); margin-top: 3px; letter-spacing: 0.03em; }
.gw-meta { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.gw-pill { font-size: 12px; color: var(--ink-3); display: inline-flex; gap: 6px; align-items: baseline; }
.gw-pill .label-eyebrow { font-size: 9px; }

/* 设备卡 */
.dev-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.dev-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px 20px;
  background: var(--surface-soft);
  transition: border-color 0.25s var(--ease);
}
.dev-card:hover { border-color: var(--sage); }
.dev-highlight {
  border-color: var(--sage) !important;
  box-shadow: 0 0 0 3px var(--sage-soft);
  animation: hl-pulse 0.6s ease-out 3;
}
@keyframes hl-pulse {
  0%, 100% { box-shadow: 0 0 0 3px var(--sage-soft); }
  50%      { box-shadow: 0 0 0 8px var(--sage-soft); }
}
.dc-row { display: flex; justify-content: space-between; align-items: center; }
.dc-title { cursor: pointer; }
.dc-title:hover .dc-name { color: var(--sage-deep); }
.dc-name { font-family: var(--font-display); font-size: 16px; font-weight: 500; }
.dc-bound {
  font-size: 9px;
  padding: 2px 8px;
  border-radius: 999px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-left: 8px;
  background: var(--paper-deep);
  color: var(--ink-4);
}
.dc-bound.bound { background: var(--sage-soft); color: var(--sage-deep); }
.dc-type { font-size: 9px; }
.dc-mac { font-size: 10px; color: var(--ink-4); margin: 6px 0 14px; letter-spacing: 0.04em; }
.dc-actions { display: flex; gap: 8px; margin-bottom: 12px; }
.dc-ctrl {
  display: flex;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}
.ctrl-btn {
  flex: 1;
  border: 1px solid var(--line-strong);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 7px;
  font-size: 12px;
  color: var(--ink-3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: all 0.2s var(--ease);
  cursor: pointer;
  font-family: var(--font-sans);
}
.ctrl-btn:hover { border-color: var(--sage); color: var(--sage-deep); }
.ctrl-btn.pending {
  cursor: progress;
  opacity: 0.7;
  border-color: var(--ink-5);
  color: var(--ink-4);
  background: var(--paper-deep);
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
  border: 1.5px solid var(--ink-4);
  border-top-color: transparent;
  transform: translateY(-50%);
  animation: ctrl-spin 0.8s linear infinite;
}
@keyframes ctrl-spin {
  to { transform: translateY(-50%) rotate(360deg); }
}
.ctrl-btn.pending .ctrl-text {
  letter-spacing: 2px;
  font-family: var(--font-mono);
}
.ctrl-btn:disabled { cursor: progress; }
.ctrl-btn.led.on {
  background: var(--sage);
  color: #06141a;
  border-color: var(--sage);
}
.ctrl-led {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--ink-5);
  transition: all 0.2s var(--ease);
}
.ctrl-btn.led.on .ctrl-led {
  background: #fff;
  box-shadow: 0 0 6px rgba(255,255,255,0.8), 0 0 12px var(--sage-soft);
}
.ctrl-btn.st.on {
  background: var(--sage);
  color: #06141a;
  border-color: var(--sage);
}
.ctrl-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--ink-5);
  transition: all 0.2s var(--ease);
}
.ctrl-btn.st.on .ctrl-dot {
  background: #fff;
  box-shadow: 0 0 6px rgba(255,255,255,0.8), 0 0 12px var(--sage-soft);
}

/* 寻找网关列表 */
.search-list { padding: 0 4px; }
.search-empty { text-align: center; padding: 40px 0; font-size: 13px; }
.search-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px;
  margin-bottom: 14px;
  background: var(--surface-soft);
}
.search-card.bound {
  border-color: var(--sage);
}
.sc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap: 8px; }
.sc-host { font-size: 18px; font-weight: 500; }
.sc-badges { display: flex; gap: 6px; align-items: center; }
.sc-tag {
  font-size: 9px;
  padding: 2px 10px;
  border-radius: 999px;
  letter-spacing: 0.08em;
}
.sc-bound-tag {
  background: var(--sage-soft) !important;
  color: var(--sage-deep) !important;
}
.sc-row { font-size: 10px; color: var(--ink-3); margin-bottom: 4px; letter-spacing: 0.03em; }
.sc-actions { display: flex; gap: 8px; align-items: center; margin-top: 14px; }

/* 数据流 */
.stream-head { padding-bottom: 12px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
.stream-list { display: flex; flex-direction: column; gap: 2px; }
.stream-row {
  padding: 12px 0;
  border-bottom: 1px dashed var(--line);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sr-time { font-size: 11px; color: var(--ink-4); }
.sr-reads { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--ink-3); }
.sr-reads b { font-weight: 400; color: var(--ink); margin-left: 3px; }

/* 空 */
.empty {
  display: flex; flex-direction: column; align-items: center; text-align: center; padding: 70px 20px;
}
.empty-art {
  width: 100px; height: 100px; border-radius: 50%; margin-bottom: 24px;
  background:
    radial-gradient(circle at 40% 35%, var(--sage-soft), transparent 60%),
    repeating-radial-gradient(circle at 50% 50%, transparent 0 8px, var(--line) 8px 9px);
  opacity: 0.7;
}
.empty h3 { font-size: 24px; font-weight: 400; margin-bottom: 10px; }
.empty p { margin-bottom: 22px; max-width: 360px; }

@media (max-width: 1100px) {
  .dev-grid { grid-template-columns: 1fr; }
}
</style>
