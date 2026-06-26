<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listGateways, listPending, approve, reject, unbind } from '@/api/gateway'
import { listDevices, bindDevice, deviceStream, sendCmd } from '@/api/device'
import { getSocket } from '@/ws/socket'

const loading = ref(true)
const gateways = ref([])
const pending = ref([])
const pendingVisible = ref(false)
const pendingLoading = ref(false)

// 设备命名弹窗
const nameDialog = reactive({ visible: false, did: null, name: '', loading: false })
// 审批弹窗
const approveDialog = reactive({ visible: false, gw: null, name: '', loading: false })
// 数据流抽屉
const streamDrawer = reactive({ visible: false, device: null, records: [], loading: false })

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

async function openPending() {
  pendingVisible.value = true
  pendingLoading.value = true
  try {
    pending.value = await listPending()
  } finally {
    pendingLoading.value = false
  }
}

function openApprove(gw) {
  approveDialog.gw = gw
  approveDialog.name = ''
  approveDialog.visible = true
}

async function doApprove() {
  approveDialog.loading = true
  try {
    await approve(approveDialog.gw.gw_uuid, approveDialog.name)
    ElMessage.success('已同意网关接入')
    approveDialog.visible = false
    await openPending()
    await loadGateways()
  } catch (e) {
  } finally {
    approveDialog.loading = false
  }
}

async function doReject(gw) {
  await ElMessageBox.confirm(`拒绝网关 ${gw.hostname || gw.gw_uuid} 接入?`, '拒绝', {
    type: 'warning'
  }).catch(() => 'cancel').then(async (v) => {
    if (v === 'cancel') return
    await reject(gw.gw_uuid)
    ElMessage.success('已拒绝')
    await openPending()
  })
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

async function doBind() {
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

async function cmd(dev, c, value) {
  try {
    await sendCmd(dev.id, c, value)
    ElMessage.success(`指令已下发:${c}=${value}`)
  } catch (e) {
  }
}

async function toggleLed(dev) {
  const cur = dev.led_status ?? 0
  const next = cur ? 0 : 1
  dev.led_status = next
  await cmd(dev, 'LED', next)
}
async function toggleStatus(dev) {
  const cur = dev.device_status ?? 0
  const next = cur ? 0 : 1
  dev.device_status = next
  await cmd(dev, 'STATUS', next)
}

// 在所有网关的设备列表中查找指定设备,返回其所在数组与索引(便于就地更新)
function findDevice(devId) {
  for (const gw of gateways.value) {
    if (!gw.devices) continue
    const idx = gw.devices.findIndex((d) => d.id === devId)
    if (idx >= 0) return { list: gw.devices, idx }
  }
  return null
}

// WS: 设备发现时刷新 + sensor_data 实时同步设备状态
function onSocket() {
  const s = getSocket()
  s.on('device_discovered', () => loadGateways())
  s.on('cmd_feedback', (p) => {
    ElMessage.success(`设备反馈:${p.cmd}=${p.value} 成功`)
  })
  s.on('sensor_data', (p) => {
    if (!p.device_id) return
    const found = findDevice(p.device_id)
    if (!found) return
    const dev = found.list[found.idx]
    // 仅同步状态字段(避免覆盖设备本身字段如 mac/name)
    if ('led_status' in p) dev.led_status = p.led_status
    if ('device_status' in p) dev.device_status = p.device_status
  })
}

onMounted(async () => {
  await loadGateways()
  onSocket()
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
        <el-button type="primary" @click="openPending">
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
            class="dev-card"
          >
            <div class="dc-row">
              <div class="dc-title" @click="openStream(dev)">
                <span class="dc-name">{{ dev.name || dev.mac }}</span>
                <span class="dc-bound" :class="{ bound: dev.bound }">{{ dev.bound ? '已绑定' : '未绑定' }}</span>
              </div>
              <span class="dc-type label-eyebrow">{{ dev.type || '未知' }}</span>
            </div>
            <div class="dc-mac mono">{{ dev.mac }}</div>

            <div class="dc-actions">
              <el-button size="small" @click="openName(dev)">命名 / 绑定</el-button>
              <el-button size="small" @click="openStream(dev)">数据流</el-button>
            </div>
            <div class="dc-ctrl">
              <button
                class="ctrl-btn led"
                :class="{ on: !!dev.led_status }"
                @click="toggleLed(dev)"
                :title="dev.led_status ? 'LED 开 · 点击关闭' : 'LED 关 · 点击开启'"
              >
                <span class="ctrl-led"></span>LED
              </button>
              <button
                class="ctrl-btn st"
                :class="{ on: !!dev.device_status }"
                @click="toggleStatus(dev)"
                :title="dev.device_status ? '运行中 · 点击进入休眠' : '休眠中 · 点击唤醒'"
              >
                <span class="ctrl-dot"></span>{{ dev.device_status ? '运行' : '休眠' }}
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
        <p class="muted">点击右上「寻找网关」,查看请求接入的网关并同意连接。</p>
        <el-button type="primary" @click="openPending">寻找网关</el-button>
      </div>
    </div>

    <!-- 寻找网关 抽屉 -->
    <el-drawer v-model="pendingVisible" title="待审网关" size="480" direction="rtl">
      <div v-loading="pendingLoading" class="pending-list">
        <div v-if="!pending.length && !pendingLoading" class="pending-empty muted">
          暂无待审网关。请确保本地网关已启动并请求接入 EMQX。
        </div>
        <div v-for="gw in pending" :key="gw.id" class="pending-card">
          <div class="pc-head">
            <span class="pc-host display">{{ gw.hostname || '未知主机' }}</span>
            <span class="pc-tag">待审</span>
          </div>
          <div class="pc-row mono">UUID · {{ gw.gw_uuid }}</div>
          <div class="pc-row mono">IP · {{ gw.ip || '—' }}</div>
          <div class="pc-row mono">注册 · {{ gw.created_at }}</div>
          <div class="pc-actions">
            <el-button type="primary" size="small" @click="openApprove(gw)">同意接入</el-button>
            <el-button size="small" @click="doReject(gw)">拒绝</el-button>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- 命名弹窗 -->
    <el-dialog v-model="nameDialog.visible" title="命名并绑定设备" width="420">
      <el-input v-model="nameDialog.name" placeholder="为设备起一个名字" maxlength="32" show-word-limit />
      <template #footer>
        <el-button @click="nameDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="nameDialog.loading" @click="doBind">绑定</el-button>
      </template>
    </el-dialog>

    <!-- 审批弹窗 -->
    <el-dialog v-model="approveDialog.visible" title="同意网关接入" width="420">
      <p class="muted" style="margin-bottom:14px">为网关命名(可选),确认后将下发审批结果。</p>
      <el-input v-model="approveDialog.name" placeholder="如:客厅网关" maxlength="32" show-word-limit />
      <template #footer>
        <el-button @click="approveDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="approveDialog.loading" @click="doApprove">同意接入</el-button>
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
              <span v-if="r.temperature !== null">T<b>{{ r.temperature }}</b></span>
              <span v-if="r.humidity !== null">H<b>{{ r.humidity }}</b></span>
              <span v-if="r.light !== null">L<b>{{ r.light }}</b></span>
              <span class="sr-led" :class="{ on: r.led_status }">LED</span>
              <span class="sr-st">{{ r.device_status }}</span>
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

/* LED 按钮:亮 = sage 实心发光 */
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

/* 状态按钮:活跃 = sage 绿色实心发光;休眠 = 中性灰 */
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

/* 待审列表 */
.pending-list { padding: 0 4px; }
.pending-empty { text-align: center; padding: 40px 0; font-size: 13px; }
.pending-card {
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 18px;
  margin-bottom: 14px;
  background: var(--surface-soft);
}
.pc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.pc-host { font-size: 18px; font-weight: 500; }
.pc-tag {
  font-size: 9px;
  padding: 2px 10px;
  border-radius: 999px;
  letter-spacing: 0.08em;
  background: var(--amber-soft);
  color: var(--amber);
}
.pc-row { font-size: 10px; color: var(--ink-3); margin-bottom: 4px; letter-spacing: 0.03em; }
.pc-actions { display: flex; gap: 8px; margin-top: 14px; }

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
.sr-led { padding: 1px 8px; border-radius: 999px; background: var(--paper-deep); }
.sr-led.on { background: var(--sage-soft); color: var(--sage-deep); }
.sr-st { text-transform: uppercase; font-size: 10px; letter-spacing: 0.06em; align-self: center; }

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
</style>
