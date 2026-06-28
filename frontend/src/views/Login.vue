<script setup>
import { reactive, ref } from 'vue'
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
const form = reactive({ username: '', password: '', confirm: '', email: '', code: '' })

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
    <!-- 左:品牌叙事 -->
    <section class="pane-left">
      <div class="atmo-bg"></div>
      <div class="pane-inner">
        <div class="brand-row rise rise-1">
          <span class="brand-mark"></span>
          <span class="brand-name display">Atmos</span>
        </div>

        <h1 class="hero display rise rise-2">
          家居环境的<br />
          <em>呼吸</em>与<em>脉搏</em>
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
            <label class="label-eyebrow">用户名</label>
            <el-input v-model="form.username" placeholder="输入用户名" size="large" />
          </div>
          <div v-if="mode === 'register'" class="field rise rise-4">
            <label class="label-eyebrow">邮箱</label>
            <el-input v-model="form.email" placeholder="输入邮箱地址" size="large" />
          </div>
          <div class="field" :class="mode === 'register' ? 'rise rise-5' : 'rise rise-4'">
            <label class="label-eyebrow">密码</label>
            <el-input v-model="form.password" type="password" show-password placeholder="输入密码" size="large" />
          </div>
          <div v-if="mode === 'register'" class="field rise rise-6">
            <label class="label-eyebrow">确认密码</label>
            <el-input v-model="form.confirm" type="password" show-password placeholder="再次输入密码" size="large" />
          </div>
          <div v-if="mode === 'register'" class="field rise rise-7">
            <label class="label-eyebrow">验证码</label>
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
            :class="mode === 'register' ? 'rise rise-8' : 'rise rise-5'"
            type="primary"
            :loading="loading"
            @click="submit"
          >{{ mode === 'login' ? '登 录' : '注 册' }}</el-button>
        </form>

        <div class="demo muted" :class="mode === 'register' ? 'rise rise-8' : 'rise rise-5'">
          <span class="label-eyebrow">演示账号</span>
          <code class="mono">admin / admin123</code>
        </div>
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
}

/* —— 左侧品牌区 —— */
.pane-left {
  position: relative;
  background: var(--paper-deep);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 56px 64px;
}
.atmo-bg {
  position: absolute;
  inset: 0;
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
.brand-mark {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, var(--sage) 0%, var(--sage-deep) 70%);
  box-shadow: 0 0 0 4px var(--sage-tint), 0 0 24px var(--sage-soft);
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
.hero em {
  font-style: italic;
  font-weight: 400;
  color: var(--sage);
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

/* —— 右侧表单区 —— */
.pane-right {
  background: var(--paper);
  display: grid;
  place-items: center;
  padding: 40px;
}
.form-wrap {
  width: 100%;
  max-width: 360px;
}
.switch {
  display: inline-flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 10px;
}
.switch button {
  background: none;
  border: none;
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 400;
  letter-spacing: -0.02em;
  color: var(--ink-4);
  transition: color 0.25s var(--ease);
  padding: 0;
}
.switch button.on {
  color: var(--ink);
}
.switch-div {
  width: 1px;
  height: 22px;
  background: var(--line-strong);
}
.form-hint {
  font-size: 13px;
  margin-bottom: 36px;
}
.field {
  margin-bottom: 20px;
}
.field label {
  display: block;
  margin-bottom: 8px;
}
.submit {
  width: 100%;
  height: 46px;
  font-size: 15px;
  letter-spacing: 0.15em;
  margin-top: 12px;
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
.demo {
  margin-top: 36px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
  background: var(--surface-soft);
}
.demo code {
  font-size: 13px;
  color: var(--sage-deep);
}

@media (max-width: 900px) {
  .auth { grid-template-columns: 1fr; }
  .pane-left { display: none; }
}
</style>
