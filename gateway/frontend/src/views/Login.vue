<script setup>
import { reactive, ref, computed, onBeforeUnmount, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register, sendCode } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { connectSocket } from '@/ws/socket'
import { useUiStore } from '@/stores/ui'
import SetupCard from '@/components/SetupCard.vue'
import DotField from '@/components/vuebits/DotField.vue'
import LetterGlitch from '@/components/vuebits/LetterGlitch.vue'
import ShuffleText from '@/components/vuebits/ShuffleText.vue'
import RotatingText from '@/components/vuebits/RotatingText.vue'
import VariableProximity from '@/components/vuebits/VariableProximity.vue'
import DecryptedText from '@/components/vuebits/DecryptedText.vue'
import Icon from '@/components/icons/Icon.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const ui = useUiStore()

const mode = ref('login')
const loading = ref(false)
const configSaved = ref(true)  // 默认 true（Web 模式直接显示登录）
const sending = ref(false)
const countdown = ref(0)
const verifyToken = ref('')
const step = ref(1)
const form = reactive({ username: '', password: '', confirm: '', email: '', code: '' })

const registerSteps = [
  { num: 1, label: '邮箱' },
  { num: 2, label: '验证' },
  { num: 3, label: '账号' }
]

let countdownTimer = null
onBeforeUnmount(() => {
  if (countdownTimer) clearInterval(countdownTimer)
})

onMounted(async () => {
  // 检测是否桌面环境
  if (window.pywebview?.api) {
    try {
      const cfg = await window.pywebview.api.get_config()
      // BACKEND_URL 非空表示已配置
      configSaved.value = !!(cfg && cfg.BACKEND_URL)
    } catch (e) {
      // 读取失败，默认显示登录（避免阻塞用户）
      configSaved.value = true
    }
  }
})

function onConfigSaved() {
  configSaved.value = true
}

function switchMode(m) {
  mode.value = m
  step.value = 1
}

async function sendVerifyCode() {
  if (!form.email) {
    ui.pushToast({ type: 'warning', title: '请先填写邮箱' })
    return
  }
  sending.value = true
  try {
    const res = await sendCode(form.email)
    verifyToken.value = res.token
    ui.pushToast({ type: 'success', title: '验证码已发送', message: res.message || '请查收邮箱' })
    countdown.value = 60
    countdownTimer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
    }, 1000)
    step.value = 2
  } catch (e) {
    verifyToken.value = ''
  } finally {
    sending.value = false
  }
}

function nextStep() {
  if (step.value === 1) {
    if (!form.email) return ui.pushToast({ type: 'warning', title: '请填写邮箱' })
    if (!verifyToken.value && countdown.value <= 0) {
      return ui.pushToast({ type: 'warning', title: '请先发送验证码' })
    }
  }
  if (step.value === 2) {
    if (!form.code) return ui.pushToast({ type: 'warning', title: '请填写验证码' })
    if (form.code.length < 6) return ui.pushToast({ type: 'warning', title: '验证码为 6 位' })
  }
  if (step.value < 3) step.value++
}

function prevStep() {
  if (step.value > 1) step.value--
}

watch(() => form.code, (v) => {
  if (mode.value === 'register' && step.value === 2 && v.length === 6) {
    nextStep()
  }
})

async function submit() {
  if (mode.value === 'login') {
    if (!form.username || !form.password) {
      ui.pushToast({ type: 'warning', title: '请填写用户名和密码' })
      return
    }
  } else {
    if (!form.username) return ui.pushToast({ type: 'warning', title: '请填写用户名' })
    if (form.password.length < 6) return ui.pushToast({ type: 'warning', title: '密码至少 6 位' })
    if (form.password !== form.confirm) return ui.pushToast({ type: 'warning', title: '两次密码不一致' })
  }
  loading.value = true
  try {
    let res
    if (mode.value === 'login') {
      res = await login(form.username, form.password)
    } else {
      res = await register(form.username, form.password, form.email, form.code, verifyToken.value)
    }
    userStore.setAuth(res.token, res.user)
    connectSocket()
    ui.pushToast({ type: 'success', title: mode.value === 'login' ? '欢迎回来' : '注册成功' })
    router.push(route.query.redirect || '/')
  } catch (e) {
    if (mode.value === 'register') step.value = 2
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth">
    <!-- 左侧:点阵背景 + 品牌叙事 -->
    <div class="auth-left">
      <DotField
        class="bg-dotfield"
        :dot-spacing="16"
        :cursor-radius="450"
        :bulge-strength="55"
        :glow-radius="180"
        :glow-color="'#0a0f08'"
      />

      <div class="brand-overlay">
        <div class="brand-row">
          <span class="brand-mark" />
          <ShuffleText
            text="Atmos"
            tag="span"
            class="brand-name"
            :duration="0.45"
            :stagger="0.05"
            :shuffle-direction="'right'"
            :trigger-on-hover="false"
            :loop="true"
            :loop-delay="4"
          />
        </div>

        <VariableProximity
          text="登录控制台"
          class="hero-title"
          :from-font-weight="100"
          :to-font-weight="900"
        />

        <div class="hero-subtitle">
          <span class="hero-subtitle-label">MQTT · 实时遥测平台 /</span>
          <RotatingText :words="['实时遥测', '历史曲线', '智能预警']" class="hero-subtitle-rotating" />
        </div>

        <div class="stat-row">
          <div class="stat">
            <div class="stat-v">5</div>
            <div class="stat-l">遥测指标</div>
          </div>
          <span class="stat-sep" />
          <div class="stat">
            <div class="stat-v">10s</div>
            <div class="stat-l">入库节流</div>
          </div>
          <span class="stat-sep" />
          <div class="stat">
            <div class="stat-v">WS</div>
            <div class="stat-l">实时推送</div>
          </div>
        </div>
      </div>

      <div class="foot-overlay">
        <DecryptedText text="v2.0 · MQTT 3.1.1 · EMQX" />
      </div>
    </div>

    <!-- 右侧:LetterGlitch 背景 + 登录卡片 -->
    <div class="auth-right">
      <LetterGlitch
        class="bg-glitch"
        :columns="26"
        :speed="0.8"
      />

      <!-- 首次启动配置卡片(未配置时显示) -->
      <div v-if="!configSaved" class="setup-overlay">
        <SetupCard @saved="onConfigSaved" />
      </div>

      <div v-else class="form-overlay">
        <div class="auth-card glass-card">
          <div class="form-head">
            <div class="mode-switch">
              <span class="mode-indicator" :class="{ right: mode === 'register' }" />
              <button
                class="mode-option"
                :class="{ active: mode === 'login' }"
                data-cursor-target
                @click="switchMode('login')"
              >登录</button>
              <button
                class="mode-option"
                :class="{ active: mode === 'register' }"
                data-cursor-target
                @click="switchMode('register')"
              >注册</button>
            </div>
            <p class="form-hint">{{ mode === 'login' ? '使用账号登录控制台' : '创建一个新账号' }}</p>
          </div>

          <!-- Stepper 指示器（仅注册模式） -->
          <Transition name="fade">
            <div v-if="mode === 'register'" class="stepper">
              <template v-for="(s, i) in registerSteps" :key="s.num">
                <div class="stepper-node" :class="{ active: step >= s.num, current: step === s.num }">
                  <span class="stepper-num">{{ step > s.num ? '✓' : s.num }}</span>
                  <span class="stepper-label">{{ s.label }}</span>
                </div>
                <div v-if="i < registerSteps.length - 1" class="stepper-line" :class="{ filled: step > s.num }" />
              </template>
            </div>
          </Transition>

          <form class="form" @submit.prevent="submit">
            <Transition name="form-swap" mode="out-in">
              <!-- 登录模式 -->
              <div v-if="mode === 'login'" key="login" class="form-pane">
                <div class="field">
                  <label class="field-label">用户名</label>
                  <input
                    v-model="form.username"
                    class="glass-input field-input"
                    placeholder="输入用户名"
                    autocomplete="username"
                  />
                </div>
                <div class="field">
                  <label class="field-label">密码</label>
                  <input
                    v-model="form.password"
                    type="password"
                    class="glass-input field-input"
                    placeholder="输入密码"
                    autocomplete="current-password"
                    @keyup.enter="submit"
                  />
                </div>
                <button
                  type="submit"
                  class="glass-btn glass-btn--primary submit-btn"
                  :disabled="loading"
                  data-cursor-target
                >
                  <Icon v-if="loading" name="refresh" :size="16" class="spin" />
                  <Icon v-else name="arrowRight" :size="16" />
                  登 录
                </button>
              </div>

              <!-- 注册 Step 1: 邮箱 -->
              <div v-else-if="step === 1" key="step1" class="form-pane">
                <div class="field">
                  <label class="field-label">邮箱地址</label>
                  <input
                    v-model="form.email"
                    type="email"
                    class="glass-input field-input"
                    placeholder="输入邮箱地址"
                    autocomplete="email"
                    @keyup.enter="sendVerifyCode"
                  />
                </div>
                <button
                  type="button"
                  class="glass-btn glass-btn--primary send-btn"
                  :disabled="!form.email || sending || countdown > 0"
                  data-cursor-target
                  @click="sendVerifyCode"
                >
                  <Icon v-if="sending" name="refresh" :size="14" class="spin" />
                  <Icon v-else name="send" :size="14" />
                  {{ countdown > 0 ? `${countdown}s 后重发` : '发送验证码' }}
                </button>
              </div>

              <!-- 注册 Step 2: 验证码 -->
              <div v-else-if="step === 2" key="step2" class="form-pane">
                <div class="field">
                  <label class="field-label">验证码</label>
                  <input
                    v-model="form.code"
                    class="glass-input field-input code-input"
                    placeholder="6 位验证码"
                    maxlength="6"
                    inputmode="numeric"
                    @input="form.code = form.code.replace(/\D/g, '')"
                  />
                </div>
                <div class="step-actions">
                  <button
                    type="button"
                    class="glass-btn step-btn step-btn--prev"
                    data-cursor-target
                    @click="prevStep"
                  >
                    <Icon name="arrowLeft" :size="14" />
                    上一步
                  </button>
                </div>
              </div>

              <!-- 注册 Step 3: 账号密码 -->
              <div v-else-if="step === 3" key="step3" class="form-pane">
                <div class="field">
                  <label class="field-label">用户名</label>
                  <input
                    v-model="form.username"
                    class="glass-input field-input"
                    placeholder="设定用户名"
                    autocomplete="username"
                  />
                </div>
                <div class="field">
                  <label class="field-label">密码</label>
                  <input
                    v-model="form.password"
                    type="password"
                    class="glass-input field-input"
                    placeholder="至少 6 位密码"
                    autocomplete="new-password"
                  />
                </div>
                <div class="field">
                  <label class="field-label">确认密码</label>
                  <input
                    v-model="form.confirm"
                    type="password"
                    class="glass-input field-input"
                    placeholder="再次输入密码"
                    autocomplete="new-password"
                    @keyup.enter="submit"
                  />
                </div>
                <div class="step-actions">
                  <button
                    type="button"
                    class="glass-btn step-btn step-btn--prev"
                    data-cursor-target
                    @click="prevStep"
                  >
                    <Icon name="arrowLeft" :size="14" />
                    上一步
                  </button>
                  <button
                    type="submit"
                    class="glass-btn glass-btn--primary step-btn"
                    :disabled="loading"
                    data-cursor-target
                  >
                    <Icon v-if="loading" name="refresh" :size="14" class="spin" />
                    完成注册
                  </button>
                </div>
              </div>
            </Transition>
          </form>

          <Transition name="fade">
            <div v-if="mode === 'login'" class="demo">
              <span class="demo-label">演示账号</span>
              <code class="demo-code">admin / admin123</code>
            </div>
          </Transition>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth {
  display: grid;
  grid-template-columns: 1fr 1fr;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg-deep);
}

/* —— 左侧区域 —— */
.auth-left {
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 56px 64px;
}
.bg-dotfield {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.9;
}

/* —— 右侧区域 —— */
.auth-right {
  position: relative;
  overflow: hidden;
  border-left: 1px solid var(--glass-border);
}
.bg-glitch {
  position: absolute;
  inset: 0;
  z-index: 0;
  opacity: 0.55;
}

/* —— 品牌叙事:左半区域底部(参照原版) —— */
.brand-overlay {
  position: relative;
  z-index: 2;
  margin-top: auto;
  margin-bottom: 80px;
  max-width: 440px;
  text-align: left;
}
.brand-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  margin-bottom: 14px;
}
.brand-mark {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, #a3e635 0%, #65a30d 70%);
  box-shadow: 0 0 0 3px rgba(132, 204, 22, 0.12), 0 0 16px rgba(132, 204, 22, 0.4);
}
.brand-name {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}
.hero-title {
  font-size: clamp(1.6rem, 3vw, 2.2rem);
  font-family: 'Roboto Flex', sans-serif;
  letter-spacing: -0.04em;
  line-height: 1;
  margin-bottom: 12px;
  color: var(--text-primary);
}
.hero-subtitle {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  letter-spacing: 0.04em;
}
.hero-subtitle-label {
  color: var(--text-tertiary);
}
.hero-subtitle-rotating {
  color: var(--mint);
  text-transform: uppercase;
}
.stat-row {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 20px;
  margin-top: 18px;
}
.stat-v {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 22px;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.02em;
}
.stat-l {
  color: var(--text-tertiary);
  margin-top: 4px;
  font-size: 9px;
  font-family: 'DM Sans', sans-serif;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.stat-sep {
  width: 1px;
  height: 22px;
  background: var(--glass-border);
}

/* —— 底部版本信息 —— */
.foot-overlay {
  position: relative;
  z-index: 2;
  margin-top: 24px;
  color: var(--text-tertiary);
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  letter-spacing: 0.1em;
}

/* —— 表单浮层:右半区域居中 —— */
.form-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
  width: 420px;
  max-width: 90%;
}

/* —— 配置卡片浮层:与登录表单共享同一居中容器 —— */
.setup-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
  width: 460px;
  max-width: 90%;
}
.auth-card {
  padding: 40px 36px;
  border-radius: var(--radius-lg);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.4),
    0 2px 8px rgba(132, 204, 22, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

/* —— 模式切换:分段控件 + 滑动指示器 —— */
.mode-switch {
  position: relative;
  display: inline-flex;
  align-items: center;
  padding: 4px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--glass-border);
  margin-bottom: 10px;
}
.mode-indicator {
  position: absolute;
  top: 4px;
  left: 4px;
  width: calc(50% - 4px);
  height: calc(100% - 8px);
  border-radius: 10px;
  background: rgba(132, 204, 22, 0.14);
  box-shadow: inset 0 0 0 1px rgba(132, 204, 22, 0.20);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform;
}
.mode-indicator.right {
  transform: translateX(100%);
}
.mode-option {
  position: relative;
  z-index: 1;
  flex: 1;
  background: none;
  border: none;
  padding: 8px 36px;
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 20px;
  letter-spacing: -0.02em;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: color 0.25s ease;
}
.mode-option.active {
  color: var(--mint);
}
.form-hint {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 36px;
}

/* —— 表单切换:纯 opacity 过渡(不触发 height/layout 变化) —— */
.form-swap-enter-active,
.form-swap-leave-active {
  transition: opacity 0.15s ease;
}
.form-swap-enter-from,
.form-swap-leave-to {
  opacity: 0;
}

/* —— 淡入淡出过渡(stepper/demo):纯 opacity —— */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* —— Stepper 指示器(与 glass-light 一致) —— */
.stepper {
  display: flex;
  align-items: center;
  margin-bottom: 28px;
  padding: 14px 12px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--glass-light);
}
.stepper-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.stepper-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: 'DM Sans', sans-serif;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  border: 1px solid var(--glass-border);
  background: var(--glass-medium);
  transition: all 0.3s ease;
}
.stepper-node.active .stepper-num {
  color: var(--bg-deep);
  background: var(--mint);
  border-color: var(--mint);
  box-shadow: 0 0 0 4px rgba(132, 204, 22, 0.12);
}
.stepper-node.current .stepper-num {
  transform: scale(1.08);
  box-shadow: 0 0 0 4px rgba(132, 204, 22, 0.18), 0 0 18px rgba(132, 204, 22, 0.4);
}
.stepper-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  transition: color 0.3s ease;
}
.stepper-node.active .stepper-label {
  color: var(--text-secondary);
}
.stepper-node.current .stepper-label {
  color: var(--mint);
}
.stepper-line {
  flex: 1;
  height: 1px;
  margin: 0 8px;
  margin-bottom: 22px;
  background: var(--glass-border);
  position: relative;
  overflow: hidden;
}
.stepper-line.filled {
  background: var(--mint);
  box-shadow: 0 0 8px rgba(132, 204, 22, 0.4);
}
.stepper-line.filled::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(163, 230, 53, 0.6), transparent);
  animation: stepper-flow 2s ease-in-out infinite;
}
@keyframes stepper-flow {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

/* —— 步骤操作按钮 —— */
.step-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}
.step-btn {
  flex: 1;
  height: 44px;
  justify-content: center;
  border-radius: 12px;
  font-size: 13px;
}
.step-btn--prev {
  flex: 1;
  background: rgba(255, 255, 255, 0.04);
}
.field {
  margin-bottom: 18px;
}
.field-label {
  display: block;
  margin-bottom: 8px;
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.field-input {
  border-radius: 12px;
}
.code-row {
  display: flex;
  gap: 10px;
}
.code-input {
  flex: 1;
}
.send-btn {
  width: 100%;
  justify-content: center;
  border-radius: 12px;
  height: 44px;
}
.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.submit-btn {
  width: 100%;
  height: 48px;
  font-size: 15px;
  letter-spacing: 0.15em;
  margin-top: 14px;
  justify-content: center;
  border-radius: 12px;
}
.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.demo {
  margin-top: 32px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px dashed var(--glass-border);
  border-radius: 12px;
  background: rgba(132, 204, 22, 0.04);
}
.demo-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.demo-code {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 13px;
  color: var(--mint);
}

.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* —— 响应式:窄屏切换为单列 —— */
@media (max-width: 900px) {
  .auth {
    grid-template-columns: 1fr;
  }
  .auth-left {
    display: none;
  }
  .auth-right {
    border-left: none;
  }
  .foot-overlay { display: none; }
}
@media (max-width: 600px) {
  .form-overlay {
    width: calc(100% - 40px);
  }
  .setup-overlay {
    width: calc(100% - 40px);
  }
  .auth-card { padding: 28px 22px; }
  .mode-option { font-size: 18px; padding: 8px 28px; }
  .form-hint { margin-bottom: 24px; }
}
</style>
