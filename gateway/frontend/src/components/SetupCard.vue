<script setup>
import { reactive, ref, computed, onMounted } from 'vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassSelect from '@/components/glass/GlassSelect.vue'
import ShuffleText from '@/components/vuebits/ShuffleText.vue'
import Icon from '@/components/icons/Icon.vue'
import { useUiStore } from '@/stores/ui'

const emit = defineEmits(['saved'])
const ui = useUiStore()

const form = reactive({
  backendUrl: '',
  emqxHost: '',
  emqxPort: 1883,
  emqxUsername: '',
  emqxPassword: '',
  serialPort: '',
  serialBaudrate: 38400
})

const serialPorts = ref([])
const testing = ref(false)
const testResult = ref('')
const testStatus = ref(null) // 'success' | 'error' | null
const refreshing = ref(false)
const saving = ref(false)
const loading = ref(true)
const notDesktop = ref(false)

const baudrateOptions = [
  { value: 9600, label: '9600' },
  { value: 38400, label: '38400' },
  { value: 115200, label: '115200' }
]

const serialPortOptions = computed(() =>
  serialPorts.value.map((p) => ({ value: p, label: p }))
)

const canSave = computed(
  () =>
    testStatus.value === 'success' &&
    !saving.value &&
    !notDesktop.value &&
    !!form.backendUrl
)

function hasApi() {
  return typeof window !== 'undefined' && !!window.pywebview?.api
}

async function loadConfig() {
  if (!hasApi()) {
    notDesktop.value = true
    loading.value = false
    return
  }
  try {
    const cfg = await window.pywebview.api.get_config()
    if (cfg && typeof cfg === 'object') {
      form.backendUrl = cfg.BACKEND_URL || ''
      form.emqxHost = cfg.EMQX_HOST || ''
      form.emqxPort = Number(cfg.EMQX_PORT) || 1883
      form.emqxUsername = cfg.EMQX_USERNAME || ''
      form.emqxPassword = cfg.EMQX_PASSWORD || ''
      form.serialPort = cfg.SERIAL_PORT || ''
      form.serialBaudrate = Number(cfg.SERIAL_BAUDRATE) || 38400
    }
  } catch (e) {
    ui.pushToast({
      type: 'warning',
      title: '读取配置失败',
      message: String(e?.message || e)
    })
  } finally {
    loading.value = false
  }
}

async function refreshPorts() {
  if (!hasApi()) return
  refreshing.value = true
  try {
    const ports = await window.pywebview.api.get_serial_ports()
    serialPorts.value = Array.isArray(ports) ? ports : []
    if (serialPorts.value.length && !serialPorts.value.includes(form.serialPort)) {
      form.serialPort = serialPorts.value[0]
    }
    ui.pushToast({
      type: 'success',
      title: '串口已刷新',
      message: `检测到 ${serialPorts.value.length} 个端口`
    })
  } catch (e) {
    ui.pushToast({
      type: 'danger',
      title: '刷新串口失败',
      message: String(e?.message || e)
    })
  } finally {
    refreshing.value = false
  }
}

async function testConnection() {
  if (!form.backendUrl || testing.value) return
  if (!hasApi()) {
    ui.pushToast({ type: 'warning', title: '当前环境不支持连接测试' })
    return
  }
  testing.value = true
  testResult.value = ''
  testStatus.value = null
  try {
    const res = await window.pywebview.api.test_backend_connection(form.backendUrl)
    if (res && res.reachable) {
      testStatus.value = 'success'
      testResult.value = `连接成功${res.latency_ms != null ? ` (延迟 ${res.latency_ms}ms)` : ''}`
    } else {
      testStatus.value = 'error'
      testResult.value = `连接失败: ${res?.error || '未知错误'}`
    }
  } catch (e) {
    testStatus.value = 'error'
    testResult.value = `连接失败: ${String(e?.message || e)}`
  } finally {
    testing.value = false
  }
}

async function save() {
  if (!canSave.value || saving.value) return
  saving.value = true
  try {
    const payload = {
      BACKEND_URL: form.backendUrl,
      EMQX_HOST: form.emqxHost,
      EMQX_PORT: Number(form.emqxPort) || 1883,
      EMQX_USERNAME: form.emqxUsername,
      EMQX_PASSWORD: form.emqxPassword,
      SERIAL_PORT: form.serialPort,
      SERIAL_BAUDRATE: Number(form.serialBaudrate) || 38400
    }
    const res = await window.pywebview.api.save_config(payload)
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: '配置已保存' })
      emit('saved')
    } else {
      ui.pushToast({
        type: 'danger',
        title: '保存失败',
        message: res?.error || '未知错误'
      })
    }
  } catch (e) {
    ui.pushToast({
      type: 'danger',
      title: '保存失败',
      message: String(e?.message || e)
    })
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadConfig()
  if (!notDesktop.value) {
    // 自动填充串口列表
    refreshPorts()
  }
})
</script>

<template>
  <div class="setup-card">
    <!-- 加载态 -->
    <div v-if="loading" class="setup-loading">
      <Icon name="refresh" :size="22" class="spin" />
      <span>加载配置中…</span>
    </div>

    <!-- 桌面端配置卡片 -->
    <GlassCard
      v-else-if="!notDesktop"
      class="setup-surface"
      :hover="false"
      :padding="''"
    >
      <div class="setup-head">
        <ShuffleText
          text="首次配置"
          tag="h2"
          class="setup-title"
          :duration="0.45"
          :stagger="0.05"
          :shuffle-direction="'right'"
          :trigger-on-hover="false"
          :loop="true"
          :loop-delay="8"
        />
        <p class="setup-subtitle">请填写服务器连接信息以初始化网关</p>
      </div>

      <form class="setup-form" @submit.prevent="save">
        <!-- 服务器配置 -->
        <div class="section">
          <div class="section-head">
            <span class="section-dot" />
            <span class="section-label">服务器配置</span>
          </div>
          <div class="field">
            <label class="field-label">云端后端地址</label>
            <div class="field-row">
              <input
                v-model="form.backendUrl"
                class="glass-input field-input"
                placeholder="https://api.example.com"
                inputmode="url"
                data-cursor-target
              />
              <button
                type="button"
                class="glass-btn test-btn"
                :disabled="!form.backendUrl || testing"
                data-cursor-target
                @click="testConnection"
              >
                <Icon v-if="testing" name="refresh" :size="14" class="spin" />
                <Icon v-else name="zap" :size="14" />
                {{ testing ? '测试中' : '测试' }}
              </button>
            </div>
            <Transition name="fade">
              <div v-if="testResult" class="test-result" :class="testStatus">
                <Icon
                  :name="testStatus === 'success' ? 'check' : 'warning'"
                  :size="13"
                />
                <span>{{ testResult }}</span>
              </div>
            </Transition>
          </div>
        </div>

        <!-- EMQX 配置 -->
        <div class="section">
          <div class="section-head">
            <span class="section-dot" />
            <span class="section-label">EMQX 配置</span>
          </div>
          <div class="grid-2">
            <div class="field">
              <label class="field-label">EMQX 主机</label>
              <input
                v-model="form.emqxHost"
                class="glass-input field-input"
                placeholder="127.0.0.1"
                data-cursor-target
              />
            </div>
            <div class="field">
              <label class="field-label">EMQX 端口</label>
              <input
                v-model.number="form.emqxPort"
                type="number"
                class="glass-input field-input"
                placeholder="1883"
                data-cursor-target
              />
            </div>
          </div>
          <div class="grid-2">
            <div class="field">
              <label class="field-label">用户名</label>
              <input
                v-model="form.emqxUsername"
                class="glass-input field-input"
                placeholder="可选"
                autocomplete="off"
                data-cursor-target
              />
            </div>
            <div class="field">
              <label class="field-label">密码</label>
              <input
                v-model="form.emqxPassword"
                type="password"
                class="glass-input field-input"
                placeholder="可选"
                autocomplete="new-password"
                data-cursor-target
              />
            </div>
          </div>
        </div>

        <!-- 串口配置 -->
        <div class="section">
          <div class="section-head">
            <span class="section-dot" />
            <span class="section-label">串口配置</span>
          </div>
          <div class="grid-2">
            <div class="field">
              <label class="field-label">串口端口</label>
              <div class="field-row">
                <GlassSelect
                  v-model="form.serialPort"
                  :options="serialPortOptions"
                  placeholder="选择串口"
                  class="field-select"
                />
                <button
                  type="button"
                  class="glass-btn icon-btn"
                  :disabled="refreshing"
                  :title="refreshing ? '刷新中' : '刷新串口'"
                  data-cursor-target
                  @click="refreshPorts"
                >
                  <Icon name="refresh" :size="14" :class="refreshing ? 'spin' : ''" />
                </button>
              </div>
            </div>
            <div class="field">
              <label class="field-label">波特率</label>
              <GlassSelect
                v-model="form.serialBaudrate"
                :options="baudrateOptions"
                placeholder="选择波特率"
                class="field-select"
              />
            </div>
          </div>
        </div>

        <button
          type="submit"
          class="glass-btn glass-btn--primary submit-btn"
          :disabled="!canSave"
          data-cursor-target
        >
          <Icon v-if="saving" name="refresh" :size="16" class="spin" />
          <Icon v-else name="arrowRight" :size="16" />
          {{ saving ? '保存中…' : '保存并继续' }}
        </button>
        <p v-if="!canSave && testStatus !== 'error'" class="save-hint">
          需先测试服务器连接成功后才能保存
        </p>
      </form>
    </GlassCard>
  </div>
</template>

<style scoped>
.setup-card {
  width: 100%;
  max-width: 460px;
}

/* 加载态 */
.setup-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 24px;
  color: var(--text-tertiary);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
}

/* —— 透明液态玻璃表面:更高透明度,更少模糊 —— */
.setup-surface {
  padding: 32px 32px 28px;
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.025);
  backdrop-filter: blur(6px) saturate(1.3);
  -webkit-backdrop-filter: blur(6px) saturate(1.3);
  border: 1px solid rgba(132, 204, 22, 0.14);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.35),
    0 2px 8px rgba(132, 204, 22, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

/* —— 标题区 —— */
.setup-head {
  margin-bottom: 22px;
}
.setup-title {
  margin: 0;
  font-family: 'Roboto Flex', 'DM Sans', sans-serif;
  font-variation-settings: 'wght' 700;
  font-size: 24px;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  line-height: 1.1;
}
.setup-subtitle {
  margin: 6px 0 0;
  font-family: 'DM Sans', sans-serif;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
}

/* —— 表单布局 —— */
.setup-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--mint);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.6);
}
.section-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.field-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.field-input {
  border-radius: 12px;
}
.field-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.field-row .field-input {
  flex: 1;
  min-width: 0;
}
.field-select {
  flex: 1;
  min-width: 0;
}
/* GlassSelect 按钮圆角与文本输入框统一 */
.field-select :deep(.glass-input) {
  border-radius: 12px;
}

/* —— 按钮 —— */
.test-btn,
.icon-btn {
  flex-shrink: 0;
  height: auto;
  padding: 0 14px;
  border-radius: 12px;
  font-size: 12px;
  white-space: nowrap;
}
.icon-btn {
  padding: 0 12px;
}
.test-btn:disabled,
.icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* —— 测试结果提示 —— */
.test-result {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  letter-spacing: 0.02em;
}
.test-result.success {
  color: var(--mint);
  background: rgba(52, 211, 153, 0.08);
  border: 1px solid rgba(52, 211, 153, 0.2);
}
.test-result.error {
  color: var(--color-danger);
  background: rgba(248, 113, 113, 0.06);
  border: 1px solid rgba(248, 113, 113, 0.18);
}

/* —— 双列网格 —— */
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

/* —— 提交按钮 —— */
.submit-btn {
  width: 100%;
  height: 46px;
  justify-content: center;
  border-radius: 12px;
  font-size: 14px;
  letter-spacing: 0.12em;
  margin-top: 4px;
}
.submit-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
  transform: none;
}
.save-hint {
  margin: -4px 0 0;
  text-align: center;
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--text-tertiary);
}

/* —— 过渡 —— */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.spin {
  animation: setup-spin 1s linear infinite;
}
@keyframes setup-spin {
  to {
    transform: rotate(360deg);
  }
}

/* —— 响应式 —— */
@media (max-width: 600px) {
  .setup-surface {
    padding: 24px 18px;
  }
  .grid-2 {
    grid-template-columns: 1fr;
  }
  .setup-title {
    font-size: 21px;
  }
}
</style>
