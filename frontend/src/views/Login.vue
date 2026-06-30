<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login, register, sendCode } from '@/api/auth'
import { useUserStore } from '@/stores/user'
import { connectSocket } from '@/ws/socket'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const mode = ref('login') // login | register
const loading = ref(false)
const sending = ref(false)
const countdown = ref(0)
const verifyToken = ref('')
const remember = ref(false)
const form = reactive({ username: '', password: '', confirm: '', email: '', code: '' })

// 星星随机位置与大小
function starStyle(i) {
  const x = Math.random() * 100
  const y = Math.random() * 100
  const size = 1 + Math.random() * 2
  const delay = Math.random() * 6
  const duration = 3 + Math.random() * 4
  return {
    left: x + '%',
    top: y + '%',
    width: size + 'px',
    height: size + 'px',
    animationDelay: delay + 's',
    animationDuration: duration + 's',
  }
}

// 页面加载时读取保存的凭据
onMounted(() => {
  const saved = localStorage.getItem('atmos_credentials')
  if (saved) {
    try {
      const { username, password } = JSON.parse(saved)
      form.username = username || ''
      form.password = password || ''
      remember.value = true
    } catch (e) {
      localStorage.removeItem('atmos_credentials')
    }
  }
})

let countdownTimer = null

async function sendVerifyCode() {
  if (!form.email) {
    ElMessage.warning('请先填写邮箱')
    return
  }
  sending.value = true
  try {
    const res = await sendCode(form.email)
    verifyToken.value = res.token
    ElMessage.success(res.message || '验证码已发送')
    countdown.value = 60
    countdownTimer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        clearInterval(countdownTimer)
        countdownTimer = null
      }
    }, 1000)
  } catch (e) {
    verifyToken.value = ''
  } finally {
    sending.value = false
  }
}

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  if (mode.value === 'register') {
    if (!form.email) return ElMessage.warning('请填写邮箱')
    if (!form.code) return ElMessage.warning('请填写验证码')
    if (form.password.length < 6) return ElMessage.warning('密码至少 6 位')
    if (form.password !== form.confirm) return ElMessage.warning('两次密码不一致')
  }
  loading.value = true
  try {
    if (mode.value === 'login') {
      const { token, user } = await login(form.username, form.password)
      userStore.setAuth(token, user)
      connectSocket()
      // 记住密码:登录成功后保存/清除
      if (remember.value) {
        localStorage.setItem('atmos_credentials', JSON.stringify({ username: form.username, password: form.password }))
      } else {
        localStorage.removeItem('atmos_credentials')
      }
      ElMessage.success('欢迎回来')
    } else {
      const { token, user } = await register(
        form.username,
        form.password,
        form.email,
        form.code,
        verifyToken.value
      )
      userStore.setAuth(token, user)
      connectSocket()
      ElMessage.success('注册成功')
    }
    router.push(route.query.redirect || '/')
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth">
    <!-- 全屏氛围背景 -->
    <div class="atmo-bg"></div>
    <div class="star-field">
      <span v-for="i in 50" :key="i" class="star" :style="starStyle(i)"></span>
    </div>

    <!-- 左:品牌叙事 -->
    <section class="pane-left">
      <div class="pane-inner">
        <div class="brand-row rise rise-1">
          <span class="brand-mark">
            <span class="brand-orbit"></span>
            <span class="brand-core"></span>
          </span>
          <span class="brand-name display">Atmos</span>
        </div>

        <h1 class="hero display rise rise-2">
          <span class="hero-line">家居环境的</span>
          <span class="hero-accent">
            <em>呼吸</em>与<em>脉搏</em>
          </span>
        </h1>

        <p class="hero-sub rise rise-3">
          基于 MQTT 协议的端到端智能家居遥测平台。<br />
          从传感器到云端,温湿光与设备状态,逐秒可见。
        </p>

        <div class="stat-row rise rise-4">
          <div class="stat">
            <div class="stat-v mono">5</div>
            <div class="stat-l label-eyebrow">遥测指标</div>
          </div>
          <div class="stat-sep"></div>
          <div class="stat">
            <div class="stat-v mono">10s</div>
            <div class="stat-l label-eyebrow">入库节流</div>
          </div>
          <div class="stat-sep"></div>
          <div class="stat">
            <div class="stat-v mono">WS</div>
            <div class="stat-l label-eyebrow">实时推送</div>
          </div>
        </div>
      </div>
      <div class="pane-foot label-eyebrow">v1.0 · MQTT 3.1.1 · EMQX</div>
    </section>

    <!-- 右:表单 -->
    <section class="pane-right">
      <div class="form-wrap">
        <div class="form-head rise rise-2">
          <div class="switch">
            <button
              :class="{ on: mode === 'login' }"
              @click="mode = 'login'"
            >登录</button>
            <span class="switch-div"></span>
            <button
              :class="{ on: mode === 'register' }"
              @click="mode = 'register'"
            >注册</button>
          </div>
          <p class="form-hint muted">{{ mode === 'login' ? '使用账号登录控制台' : '创建一个新账号' }}</p>
        </div>

        <form class="form" @submit.prevent="submit">
          <div class="field rise rise-3">
            <label class="label-eyebrow">
              <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                <circle cx="12" cy="7" r="4"/>
              </svg>
              用户名
            </label>
            <el-input v-model="form.username" placeholder="输入用户名" size="large" />
          </div>
          <div v-if="mode === 'register'" class="field rise rise-4">
            <label class="label-eyebrow">
              <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/>
                <polyline points="22,6 12,13 2,6"/>
              </svg>
              邮箱
            </label>
            <el-input v-model="form.email" placeholder="输入邮箱地址" size="large" />
          </div>
          <div class="field" :class="mode === 'register' ? 'rise rise-5' : 'rise rise-4'">
            <label class="label-eyebrow">
              <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              密码
            </label>
            <el-input v-model="form.password" type="password" show-password placeholder="输入密码" size="large" />
          </div>
          <div v-if="mode === 'login'" class="remember-row">
            <el-checkbox v-model="remember">记住密码</el-checkbox>
          </div>
          <div v-if="mode === 'register'" class="field rise rise-6">
            <label class="label-eyebrow">
              <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
                <circle cx="12" cy="16" r="1"/>
              </svg>
              确认密码
            </label>
            <el-input v-model="form.confirm" type="password" show-password placeholder="再次输入密码" size="large" />
          </div>
          <div v-if="mode === 'register'" class="field rise rise-7">
            <label class="label-eyebrow">
              <svg class="field-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                <polyline points="22 4 12 14.01 9 11.01"/>
              </svg>
              验证码
            </label>
            <div class="code-row">
              <el-input
                v-model="form.code"
                class="code-input"
                placeholder="6位验证码"
                maxlength="6"
                size="large"
                @input="form.code = form.code.replace(/\D/g, '')"
              />
              <el-button
                class="send-btn"
                size="large"
                :disabled="!form.email || sending || countdown > 0"
                :loading="sending"
                @click="sendVerifyCode"
              >{{ countdown > 0 ? `${countdown}s` : '发送验证码' }}</el-button>
            </div>
          </div>

          <el-button
            class="submit"
            :class="mode === 'register' ? 'rise rise-8' : 'rise rise-6'"
            type="primary"
            :loading="loading"
            @click="submit"
          >
            <span class="btn-content">
              <svg v-if="!loading" class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path v-if="mode === 'login'" d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4M10 17l5-5-5-5M15 12H3"/>
                <path v-else d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M8.5 7a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM20 8v6M23 11h-6"/>
              </svg>
              {{ mode === 'login' ? '登 录' : '注 册' }}
            </span>
          </el-button>
        </form>
      </div>
    </section>
  </div>
</template>

<style scoped>
.auth {
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  height: 100vh;
  overflow: hidden;
  position: relative;
  background: var(--paper-deep);
}

/* —— 全屏氛围背景 —— */
.atmo-bg {
  position: absolute;
  inset: 0;
  z-index: 0;
  background:
    radial-gradient(900px 600px at 12% 110%, var(--glow-1), transparent 55%),
    radial-gradient(700px 500px at 95% 8%, var(--glow-2), transparent 55%),
    radial-gradient(500px 400px at 60% 60%, var(--amber-soft), transparent 60%);
}
.atmo-bg::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: radial-gradient(ellipse at 50% 50%, #000 30%, transparent 80%);
  -webkit-mask-image: radial-gradient(ellipse at 50% 50%, #000 30%, transparent 80%);
}

/* 星空背景 */
.star-field {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}
.star {
  position: absolute;
  background: var(--sage);
  border-radius: 50%;
  opacity: 0;
  animation: twinkle infinite;
  box-shadow: 0 0 4px var(--sage-soft);
}
@keyframes twinkle {
  0%, 100% { opacity: 0; transform: scale(0.5); }
  50% { opacity: 0.8; transform: scale(1); }
}

/* —— 左侧品牌区(透明,背景由 .auth 全屏承载) —— */
.pane-left {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  padding: 56px 64px;
  background: transparent;
}

.pane-inner {
  position: relative;
  z-index: 1;
  margin-top: auto;
  margin-bottom: 80px;
  color: var(--ink);
}
.brand-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 44px;
}

/* 品牌标识:轨道动画 */
.brand-mark {
  position: relative;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.brand-core {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, var(--sage) 0%, var(--sage-deep) 70%);
  box-shadow: 0 0 16px var(--sage-soft);
  z-index: 2;
}
.brand-orbit {
  position: absolute;
  inset: 0;
  border: 1.5px solid var(--sage);
  border-radius: 50%;
  opacity: 0.6;
  animation: orbit-spin 8s linear infinite;
}
.brand-orbit::before {
  content: '';
  position: absolute;
  top: -3px;
  left: 50%;
  width: 6px;
  height: 6px;
  background: var(--sage);
  border-radius: 50%;
  box-shadow: 0 0 8px var(--sage);
  transform: translateX(-50%);
}
@keyframes orbit-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.brand-name {
  font-size: 30px;
  font-weight: 500;
  letter-spacing: -0.02em;
}
.hero {
  font-size: 52px;
  line-height: 1.08;
  font-weight: 300;
  letter-spacing: -0.03em;
  margin-bottom: 22px;
}
.hero-line {
  display: block;
  opacity: 0;
  animation: fade-up 0.8s var(--ease) 0.2s forwards;
}
.hero-accent {
  display: block;
  margin-top: 8px;
  opacity: 0;
  animation: fade-up 0.8s var(--ease) 0.4s forwards;
}
.hero em {
  font-style: italic;
  font-weight: 400;
  color: var(--sage);
  text-shadow: 0 0 20px var(--sage-soft);
}
@keyframes fade-up {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.hero-sub {
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-3);
  max-width: 440px;
}
.stat-row {
  display: flex;
  align-items: center;
  gap: 28px;
  margin-top: 48px;
}
.stat-v {
  font-size: 30px;
  font-weight: 300;
  color: var(--ink);
  line-height: 1;
}
.stat-l {
  color: var(--ink-4);
  margin-top: 8px;
  font-size: 9px;
}
.stat-sep {
  width: 1px;
  height: 32px;
  background: var(--line-strong);
}
.pane-foot {
  position: relative;
  z-index: 1;
  color: var(--ink-4);
  margin-top: 24px;
}

/* —— 右侧表单区(毛玻璃) —— */
.pane-right {
  display: grid;
  place-items: center;
  padding: 40px;
  position: relative;
  z-index: 1;
  overflow: hidden;
  background: transparent;
  backdrop-filter: blur(24px) saturate(140%);
  -webkit-backdrop-filter: blur(24px) saturate(140%);
}
/* 毛玻璃面板的细微光泽 */
.pane-right::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(
    135deg,
    color-mix(in srgb, var(--paper) 25%, transparent) 0%,
    color-mix(in srgb, var(--paper) 8%, transparent) 50%,
    color-mix(in srgb, var(--paper) 18%, transparent) 100%
  );
  pointer-events: none;
  z-index: -1;
}
.pane-right::after {
  content: '';
  position: absolute;
  top: -50%;
  right: -30%;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, var(--glow-1), transparent 70%);
  opacity: 0.18;
  pointer-events: none;
  z-index: -1;
}

.form-wrap {
  width: 100%;
  max-width: 380px;
  position: relative;
  z-index: 1;
  background: color-mix(in srgb, var(--surface) 55%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 40px;
  border-radius: 20px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.12),
    inset 0 1px 0 color-mix(in srgb, var(--paper) 40%, transparent);
  border: 1px solid color-mix(in srgb, var(--line-strong) 40%, transparent);
}
.switch {
  display: inline-flex;
  align-items: center;
  gap: 24px;
  margin-bottom: 12px;
  position: relative;
}
.switch button {
  background: none;
  border: none;
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink-5);
  transition: color 0.3s var(--ease), transform 0.3s var(--ease);
  padding: 0;
  cursor: pointer;
}
.switch button.on {
  color: var(--ink);
  transform: scale(1.05);
}
.switch button:hover:not(.on) {
  color: var(--ink-3);
}
.switch-div {
  width: 1px;
  height: 24px;
  background: var(--line-strong);
}
.form-hint {
  font-size: 13px;
  margin-bottom: 36px;
  color: var(--ink-3);
}
.field {
  margin-bottom: 22px;
}
.field label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  color: var(--ink-3);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.field-icon {
  width: 14px;
  height: 14px;
  opacity: 0.6;
  transition: opacity 0.3s var(--ease), color 0.3s var(--ease);
}
.field:focus-within .field-icon {
  opacity: 1;
  color: var(--sage);
}
.submit {
  width: 100%;
  height: 48px;
  font-size: 15px;
  letter-spacing: 0.18em;
  margin-top: 16px;
  transition: transform 0.2s var(--ease), box-shadow 0.3s var(--ease), background 0.3s var(--ease);
  position: relative;
  overflow: hidden;
}
.submit::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, transparent 30%, rgba(255,255,255,0.15) 50%, transparent 70%);
  transform: translateX(-100%);
  transition: transform 0.6s ease;
}
.submit:hover::before {
  transform: translateX(100%);
}
.submit:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px var(--sage-soft);
}
.submit:active {
  transform: translateY(0);
}
.btn-content {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.btn-icon {
  width: 18px;
  height: 18px;
  transition: transform 0.3s var(--ease);
}
.submit:hover .btn-icon {
  transform: translateX(3px);
}
.code-row {
  display: flex;
  gap: 10px;
}
.code-input {
  flex: 1;
}
.send-btn {
  flex-shrink: 0;
  min-width: 120px;
}
.remember-row {
  margin-top: -6px;
  margin-bottom: 18px;
}
.remember-row :deep(.el-checkbox__label) {
  color: var(--ink-3);
  font-size: 13px;
}

@media (max-width: 900px) {
  .auth { grid-template-columns: 1fr; }
  .pane-left { display: none; }
}
</style>
