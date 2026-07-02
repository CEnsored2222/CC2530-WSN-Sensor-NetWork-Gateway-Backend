<script setup>
import { ref, onMounted, onUnmounted, computed, nextTick } from 'vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import Icon from '@/components/icons/Icon.vue'

const loading = ref(true)

// 网关状态
const gatewayStatus = ref({
  gateway_running: false,
  serial_open: false,
  serial_port: '',
  serial_baudrate: 115200,
  emqx_connected: false,
  emqx_host: '',
  emqx_port: 1883
})

// 串口配置
const serialPorts = ref([])
const selectedSerialPort = ref('')
const selectedBaudrate = ref(115200)
const serialSaving = ref(false)

const baudrateOptions = [9600, 19200, 38400, 57600, 115200, 230400, 460800]

// EMQX 配置
const emqxConfig = ref({
  host: '',
  port: 1883,
  username: '',
  password: ''
})
const emqxSaving = ref(false)

// 日志
const logs = ref([])
const logScrollEl = ref(null)

// 轮询定时器
let statusTimer = null
let logTimer = null

async function loadStatus() {
  try {
    const s = await window.pywebview.api.get_gateway_status()
    gatewayStatus.value = s
  } catch (e) {
    /* 静默 */
  } finally {
    if (loading.value) loading.value = false
  }
}

async function loadSerialPorts() {
  try {
    const res = await window.pywebview.api.list_serial_ports()
    serialPorts.value = res.ports || []
  } catch (e) {
    serialPorts.value = []
  }
}

async function loadLogs() {
  try {
    const res = await window.pywebview.api.get_gateway_logs()
    const newLines = res.logs || []
    if (newLines.length > 0) {
      const el = logScrollEl.value
      // 保存更新前的滚动状态：普通 flex-direction 下 scrollTop=0=顶部(最旧消息)
      // 用户查看最新消息时 scrollTop ≈ scrollHeight - clientHeight
      const prevScrollTop = el ? el.scrollTop : 0
      const prevScrollHeight = el ? el.scrollHeight : 0
      const prevClientHeight = el ? el.clientHeight : 0
      // 判断是否在底部（最新消息区域）：距底部 < 30px
      const wasAtLatest = prevScrollHeight - prevClientHeight - prevScrollTop < 30

      // 新日志追加到尾部(最新消息在列表末尾/视觉底部)
      logs.value = [...logs.value, ...newLines].slice(-500)

      // 等待 Vue DOM 更新完成后再设置滚动位置
      await nextTick()
      if (el) {
        if (wasAtLatest) {
          // 用户在底部→自动滚到底部(最新消息)
          el.scrollTop = el.scrollHeight
        } else {
          // 用户正在查看历史→保持原内容位置不变
          el.scrollTop = prevScrollTop + (el.scrollHeight - prevScrollHeight)
        }
      }
    }
  } catch (e) {
    /* 静默 */
  }
}

async function startGateway() {
  try {
    await window.pywebview.api.start_gateway()
    await loadStatus()
  } catch (e) {
    /* 静默 */
  }
}

async function stopGateway() {
  try {
    await window.pywebview.api.stop_gateway()
    await loadStatus()
  } catch (e) {
    /* 静默 */
  }
}

async function saveSerialConfig() {
  serialSaving.value = true
  try {
    await window.pywebview.api.save_serial_config({
      port: selectedSerialPort.value,
      baudrate: selectedBaudrate.value
    })
    await loadStatus()
  } catch (e) {
    /* 静默 */
  } finally {
    serialSaving.value = false
  }
}

async function saveEmqxConfig() {
  emqxSaving.value = true
  try {
    await window.pywebview.api.save_emqx_config({
      host: emqxConfig.value.host,
      port: emqxConfig.value.port,
      username: emqxConfig.value.username,
      password: emqxConfig.value.password
    })
    await loadStatus()
  } catch (e) {
    /* 静默 */
  } finally {
    emqxSaving.value = false
  }
}

async function refreshSerialPorts() {
  await loadSerialPorts()
}

const gatewayRunningLabel = computed(() => gatewayStatus.value.gateway_running ? '运行中' : '已停止')
const serialLabel = computed(() => gatewayStatus.value.serial_open ? '已连接' : '未连接')
const emqxLabel = computed(() => gatewayStatus.value.emqx_connected ? '已连接' : '未连接')

const statusPills = computed(() => [
  {
    key: 'gateway',
    label: '网关',
    value: gatewayRunningLabel.value,
    connected: gatewayStatus.value.gateway_running,
    icon: 'gateway'
  },
  {
    key: 'serial',
    label: '串口',
    value: serialLabel.value,
    connected: gatewayStatus.value.serial_open,
    detail: gatewayStatus.value.serial_open ? `${gatewayStatus.value.serial_port} @ ${gatewayStatus.value.serial_baudrate}` : '',
    icon: 'cpu'
  },
  {
    key: 'emqx',
    label: 'EMQX',
    value: emqxLabel.value,
    connected: gatewayStatus.value.emqx_connected,
    detail: gatewayStatus.value.emqx_connected ? `${gatewayStatus.value.emqx_host}:${gatewayStatus.value.emqx_port}` : '',
    icon: 'wifi'
  }
])

// 检查 api 是否存在
function hasApi(name) {
  return typeof window.pywebview?.api?.[name] === 'function'
}

onMounted(async () => {
  await loadStatus()
  // 从状态初始化表单（仅一次，避免轮询覆盖用户输入）
  const s = gatewayStatus.value
  if (s.serial_port) selectedSerialPort.value = s.serial_port
  if (s.serial_baudrate) selectedBaudrate.value = s.serial_baudrate
  if (s.emqx_host != null) emqxConfig.value.host = s.emqx_host
  if (s.emqx_port != null) emqxConfig.value.port = s.emqx_port

  await loadSerialPorts()
  await loadLogs()

  statusTimer = setInterval(loadStatus, 2000)
  logTimer = setInterval(loadLogs, 1500)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  if (logTimer) clearInterval(logTimer)
})
</script>

<template>
  <div class="gateway page-container">
    <PageHeader
      title="网关控制"
      eyebrow="GATEWAY"
      :rotating-words="['串口', 'EMQX', '传感器', '数据流']"
    />

    <!-- 状态胶囊 -->
    <div class="status-bar">
      <div
        v-for="pill in statusPills"
        :key="pill.key"
        class="status-pill glass-card"
        :class="{ 'status-pill--connected': pill.connected }"
      >
        <div class="pill-icon">
          <Icon :name="pill.icon" :size="18" />
        </div>
        <div class="pill-body">
          <span class="pill-label eyebrow">{{ pill.label }}</span>
          <span class="pill-value">{{ pill.value }}</span>
          <span v-if="pill.detail" class="pill-detail">{{ pill.detail }}</span>
        </div>
        <span class="pill-dot" :class="pill.connected ? 'status-dot--connected' : 'status-dot--disconnected'" />
      </div>
    </div>

    <!-- 网关启停 -->
    <div v-if="hasApi('start_gateway') && hasApi('stop_gateway')" class="gateway-control glass-card">
      <div class="control-head">
        <Icon name="gateway" :size="18" />
        <span class="control-title">网关控制</span>
      </div>
      <div class="control-body">
        <p class="control-desc">
          当前状态：
          <span :style="{ color: gatewayStatus.gateway_running ? 'var(--mint)' : 'var(--text-tertiary)' }">
            {{ gatewayStatus.gateway_running ? '运行中' : '已停止' }}
          </span>
        </p>
        <div class="control-actions">
          <button
            type="button"
            class="glass-btn glass-btn--primary"
            :disabled="gatewayStatus.gateway_running"
            data-cursor-target
            @click="startGateway"
          >
            <Icon name="play" :size="14" />
            <span>启动网关</span>
          </button>
          <button
            type="button"
            class="glass-btn"
            :disabled="!gatewayStatus.gateway_running"
            data-cursor-target
            @click="stopGateway"
          >
            <Icon name="pause" :size="14" />
            <span>停止网关</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 配置卡片双栏 -->
    <div class="config-grid">
      <!-- EMQX 配置 -->
      <div class="glass-card config-card">
        <div class="config-head">
          <Icon name="wifi" :size="16" />
          <span class="config-title">EMQX 配置</span>
          <span
            class="config-status-dot"
            :class="gatewayStatus.emqx_connected ? 'status-dot--connected' : 'status-dot--disconnected'"
          />
        </div>
        <div class="config-form">
          <label class="config-field">
            <span class="config-label eyebrow">主机地址</span>
            <input
              v-model="emqxConfig.host"
              type="text"
              class="glass-input"
              placeholder="如 localhost 或 192.168.1.100"
            />
          </label>
          <label class="config-field">
            <span class="config-label eyebrow">端口</span>
            <input
              v-model.number="emqxConfig.port"
              type="number"
              class="glass-input"
              placeholder="1883"
            />
          </label>
          <label class="config-field">
            <span class="config-label eyebrow">用户名</span>
            <input
              v-model="emqxConfig.username"
              type="text"
              class="glass-input"
              placeholder="可选"
            />
          </label>
          <label class="config-field">
            <span class="config-label eyebrow">密码</span>
            <input
              v-model="emqxConfig.password"
              type="password"
              class="glass-input"
              placeholder="可选"
            />
          </label>
          <div class="config-footer">
            <button
              type="button"
              class="glass-btn glass-btn--primary"
              :disabled="emqxSaving"
              data-cursor-target
              @click="saveEmqxConfig"
            >
              <Icon v-if="emqxSaving" name="refresh" :size="14" class="spin" />
              <Icon v-else name="check" :size="14" />
              <span>保存配置</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 串口配置 -->
      <div class="glass-card config-card">
        <div class="config-head">
          <Icon name="cpu" :size="16" />
          <span class="config-title">串口配置</span>
          <span
            class="config-status-dot"
            :class="gatewayStatus.serial_open ? 'status-dot--connected' : 'status-dot--disconnected'"
          />
        </div>
        <div class="config-form">
          <label class="config-field">
            <span class="config-label eyebrow">串口端口</span>
            <div class="config-select-row">
              <select v-model="selectedSerialPort" class="glass-input config-select">
                <option value="" disabled>请选择串口</option>
                <option v-for="p in serialPorts" :key="p" :value="p">{{ p }}</option>
              </select>
              <button
                type="button"
                class="glass-btn config-refresh-btn"
                data-cursor-target
                @click="refreshSerialPorts"
              >
                <Icon name="refresh" :size="14" />
              </button>
            </div>
          </label>
          <label class="config-field">
            <span class="config-label eyebrow">波特率</span>
            <select v-model.number="selectedBaudrate" class="glass-input config-select">
              <option v-for="b in baudrateOptions" :key="b" :value="b">{{ b }}</option>
            </select>
          </label>
          <div class="config-footer">
            <button
              type="button"
              class="glass-btn glass-btn--primary"
              :disabled="serialSaving"
              data-cursor-target
              @click="saveSerialConfig"
            >
              <Icon v-if="serialSaving" name="refresh" :size="14" class="spin" />
              <Icon v-else name="check" :size="14" />
              <span>保存配置</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 实时日志 -->
    <div class="glass-card log-card">
      <div class="config-head">
        <Icon name="command" :size="16" />
        <span class="config-title">实时日志</span>
        <span class="log-count eyebrow">{{ logs.length }} 条</span>
      </div>
      <div v-if="!logs.length" class="log-empty">
        <Icon name="activity" :size="32" class="opacity-30 mb-2" />
        <p style="color: var(--text-tertiary); font-size: 13px;">暂无日志…</p>
      </div>
      <div v-else ref="logScrollEl" class="log-scroll">
        <div v-for="(line, i) in logs" :key="i" class="log-line">
          <span class="log-index">{{ String(logs.length - i).padStart(3, '0') }}</span>
          <span class="log-text" :class="'log-level--' + (line.level || 'info')">{{ line.text || line }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gateway { }

/* 状态胶囊条 */
.status-bar {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 1.25rem;
}
@media (max-width: 768px) {
  .status-bar {
    grid-template-columns: 1fr;
  }
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 1rem 1.25rem;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
}
.status-pill--connected {
  border-color: rgba(52, 211, 153, 0.25);
  box-shadow:
    0 4px 16px rgba(0, 0, 0, 0.08),
    0 0 24px rgba(52, 211, 153, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.pill-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.status-pill--connected .pill-icon {
  color: var(--mint);
}
.pill-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.pill-label {
  margin-bottom: 0;
}
.pill-value {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 15px;
  color: var(--text-primary);
}
.pill-detail {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pill-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pill-dot.status-dot--connected {
  background: var(--mint);
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.12), 0 0 10px rgba(52, 211, 153, 0.5);
}
.pill-dot.status-dot--disconnected {
  background: var(--text-tertiary);
}

/* 网关启停 */
.gateway-control {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.25rem;
}
.control-head {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}
.control-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.control-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.control-desc {
  font-size: 14px;
  color: var(--text-secondary);
}
.control-actions {
  display: flex;
  gap: 10px;
}

@media (max-width: 640px) {
  .control-body {
    flex-direction: column;
    align-items: flex-start;
  }
}

/* 双栏配置卡片 */
.config-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.25rem;
}
@media (max-width: 768px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}

.config-card {
  padding: 1.25rem 1.5rem;
  display: flex;
  flex-direction: column;
}
.config-head {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-secondary);
  margin-bottom: 1rem;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--glass-border);
}
.config-title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 15px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  flex: 1;
}
.config-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.config-status-dot.status-dot--connected {
  background: var(--mint);
  box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.12), 0 0 8px rgba(52, 211, 153, 0.5);
}
.config-status-dot.status-dot--disconnected {
  background: var(--text-tertiary);
}

.config-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
}
.config-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.config-label {
  margin-bottom: 0;
}

.config-select-row {
  display: flex;
  gap: 8px;
}
.config-select {
  flex: 1;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23999' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 36px;
  cursor: pointer;
}
.config-refresh-btn {
  padding: 0.7rem 0.9rem;
  flex-shrink: 0;
}

.config-footer {
  padding-top: 4px;
}

/* 日志卡片 */
.log-card {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}
.log-count {
  margin-bottom: 0;
  flex-shrink: 0;
}
.log-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2rem 0;
}
.log-scroll {
  max-height: 400px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.log-line {
  display: flex;
  gap: 12px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  transition: background 0.15s ease;
  align-items: baseline;
}
.log-line:hover {
  background: rgba(132, 204, 22, 0.04);
}
.log-index {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--text-tertiary);
  flex-shrink: 0;
  letter-spacing: 0.06em;
  min-width: 28px;
}
.log-text {
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-secondary);
  word-break: break-all;
  line-height: 1.5;
}

.spin {
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
