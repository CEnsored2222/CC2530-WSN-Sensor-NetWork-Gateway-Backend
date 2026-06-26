<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listSubscriptions, toggleSubscription } from '@/api/subscription'

const loading = ref(true)
const items = ref([])

const META = {
  temperature: { label: '温度', desc: '环境温度采集,单位 °C', icon: 'T' },
  humidity: { label: '湿度', desc: '空气相对湿度,单位 %', icon: 'H' },
  light: { label: '光照', desc: '环境光强采集,单位 lx', icon: 'L' },
  led_status: { label: 'LED 状态', desc: '设备 LED 开关状态上报', icon: '◉' },
  device_status: { label: '设备状态', desc: '设备活跃/休眠状态上报', icon: '◐' }
}

async function load() {
  loading.value = true
  try {
    items.value = await listSubscriptions()
  } finally {
    loading.value = false
  }
}

async function toggle(item) {
  // 注意:el-switch @change 在 v-model 更新后触发,此时 item.subscribed 已是新值
  const next = item.subscribed
  try {
    const updated = await toggleSubscription(item.metric, next)
    Object.assign(item, updated)
    ElMessage.success(`${META[item.metric].label} 订阅已${next ? '开启' : '关闭'}`)
  } catch (e) {
    /* 失败回滚:恢复为原状态 */
    item.subscribed = !next
  }
}

onMounted(load)
</script>

<template>
  <div class="sub">
    <section class="head rise rise-1">
      <div>
        <div class="label-eyebrow">Admin · Subscription</div>
        <h2 class="title display">订阅管理</h2>
        <p class="sub-desc muted">
          控制后端对各遥测指标的 MQTT 订阅。关闭某项后,后端将取消该指标订阅,数据不再入库与推送。
        </p>
      </div>
      <div class="head-stat">
        <div class="hs-num display mono">{{ items.filter(i => i.subscribed).length }}<span>/{{ items.length }}</span></div>
        <div class="label-eyebrow">订阅中</div>
      </div>
    </section>

    <div class="list" v-loading="loading">
      <article
        v-for="(item, i) in items"
        :key="item.id"
        class="row rise"
        :class="{ on: item.subscribed }"
        :style="{ animationDelay: 0.1 + i * 0.06 + 's' }"
      >
        <div class="row-icon">{{ META[item.metric]?.icon }}</div>
        <div class="row-body">
          <div class="row-name display">{{ META[item.metric]?.label }}</div>
          <div class="row-desc muted">{{ META[item.metric]?.desc }}</div>
          <div class="row-meta mono">
            <span>{{ item.metric }}</span>
            <span v-if="item.updated_at">· 最近变更 {{ item.updated_at }}</span>
          </div>
        </div>
        <div class="row-switch">
          <el-switch
            v-model="item.subscribed"
            @change="toggle(item)"
          />
          <span class="row-state" :class="{ on: item.subscribed }">
            {{ item.subscribed ? '订阅中' : '已停订' }}
          </span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.sub { max-width: 920px; }

.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  padding-bottom: 26px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 24px;
}
.title { font-size: 28px; font-weight: 400; letter-spacing: -0.02em; margin-top: 6px; }
.sub-desc { font-size: 13px; line-height: 1.7; max-width: 520px; margin-top: 10px; }
.head-stat { text-align: right; }
.hs-num {
  font-size: 44px;
  font-weight: 300;
  line-height: 1;
  letter-spacing: -0.03em;
}
.hs-num span { color: var(--ink-4); }

.list { display: flex; flex-direction: column; gap: 12px; }
.row {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center;
  gap: 18px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 22px 26px;
  transition: border-color 0.3s var(--ease), background 0.3s var(--ease);
}
.row.on {
  border-color: var(--sage);
  background: linear-gradient(90deg, var(--sage-tint), var(--surface) 40%);
}
.row-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--font-mono);
  font-size: 18px;
  color: var(--ink-3);
  background: var(--paper-deep);
  transition: all 0.3s var(--ease);
}
.row.on .row-icon {
  background: var(--sage-soft);
  color: var(--sage-deep);
}
.row-name { font-size: 20px; font-weight: 500; letter-spacing: -0.01em; }
.row-desc { font-size: 13px; margin-top: 3px; }
.row-meta {
  font-size: 10px;
  color: var(--ink-4);
  margin-top: 8px;
  letter-spacing: 0.03em;
}
.row-switch {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.row-state {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-4);
}
.row-state.on { color: var(--sage-deep); }
</style>
