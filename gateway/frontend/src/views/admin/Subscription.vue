<script setup>
import { ref, computed, onMounted } from 'vue'
import { listSubscriptions, toggleSubscription } from '@/api/subscription'
import { useUiStore } from '@/stores/ui'
import PageHeader from '@/components/layout/PageHeader.vue'
import GlassStat from '@/components/layout/GlassStat.vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import GlassEmpty from '@/components/glass/GlassEmpty.vue'
import AnimatedContent from '@/components/vuebits/AnimatedContent.vue'
import FadeContent from '@/components/vuebits/FadeContent.vue'
import Icon from '@/components/icons/Icon.vue'

const ui = useUiStore()

const loading = ref(true)
const items = ref([])

const METRIC_META = {
  temperature:   { label: '温度',     unit: '°C',  icon: 'thermometer', accent: 'amber', desc: '传感器实时温度读数' },
  humidity:      { label: '湿度',     unit: '%',   icon: 'droplet',    accent: 'teal',  desc: '传感器实时湿度读数' },
  light:         { label: '光照',     unit: 'lux', icon: 'sun',        accent: 'sage',  desc: '光敏电阻实时读数' },
  led_status:    { label: 'LED 状态', unit: '',    icon: 'zap',        accent: 'mint',  desc: '设备 LED 开关状态' },
  device_status: { label: '设备状态', unit: '',    icon: 'activity',   accent: 'sage',  desc: '设备运行 / 休眠状态' }
}

const subscribedCount = computed(() => items.value.filter((i) => i.subscribed).length)

async function load() {
  loading.value = true
  try {
    items.value = await listSubscriptions() || []
  } catch (e) {} finally {
    loading.value = false
  }
}

async function onToggle(item) {
  const next = item.subscribed
  try {
    const updated = await toggleSubscription(item.metric, next)
    if (updated) Object.assign(item, updated)
    ui.pushToast({
      type: 'success',
      title: next ? '已订阅' : '已取消订阅',
      message: METRIC_META[item.metric]?.label || item.metric
    })
  } catch (e) {
    item.subscribed = !next
  }
}

onMounted(load)
</script>

<template>
  <div class="subscription page-container">
    <PageHeader
      title="订阅管理"
      eyebrow="SUBSCRIPTION"
      :rotating-words="['温度', '湿度', '光照', 'LED', '设备状态']"
    />

    <div class="stats-grid">
      <GlassStat
        label="订阅通道"
        :value="subscribedCount"
        unit="/"
        :eyebrow="`OF ${items.length}`"
        icon="subscription"
        accent="sage"
      />
      <GlassStat
        label="总通道数"
        :value="items.length"
        unit="条"
        eyebrow="TOTAL"
        icon="layers"
        accent="teal"
      />
    </div>

    <div v-if="loading" class="loading-grid">
      <div v-for="i in 4" :key="i" class="glass-skeleton" style="height: 120px; border-radius: var(--radius-lg)" />
    </div>

    <div v-else-if="!items.length" class="empty-wrap">
      <GlassCard padding="p-8" :hover="false">
        <GlassEmpty
          icon="subscription"
          title="暂无订阅通道"
          description="系统初始化后,可订阅的指标通道将在此显示。"
        />
      </GlassCard>
    </div>

    <AnimatedContent v-else :distance="60" direction="up" :duration="0.6">
      <div class="sub-grid">
        <FadeContent
          v-for="(item, i) in items"
          :key="item.id || item.metric"
          :distance="20"
          :delay="Math.min(i * 0.05, 0.4)"
        >
          <GlassCard padding="p-5" class="sub-card" :class="{ on: item.subscribed }">
            <div class="sub-head">
              <div class="sub-icon" :class="`accent-${METRIC_META[item.metric]?.accent || 'sage'}`">
                <Icon :name="METRIC_META[item.metric]?.icon || 'activity'" :size="18" />
              </div>
              <div class="min-w-0">
                <div class="sub-label">{{ METRIC_META[item.metric]?.label || item.metric }}</div>
                <div class="sub-metric data-value">{{ item.metric }}</div>
              </div>
              <span class="sub-unit" v-if="METRIC_META[item.metric]?.unit">
                {{ METRIC_META[item.metric].unit }}
              </span>
            </div>

            <p class="sub-desc">{{ METRIC_META[item.metric]?.desc || '—' }}</p>

            <div class="sub-foot">
              <span v-if="item.updated_at" class="sub-time data-value">
                {{ String(item.updated_at).replace('T', ' ').slice(0, 19) }}
              </span>
              <span v-else class="sub-time">尚未操作</span>

              <button
                class="sub-toggle"
                :class="{ on: item.subscribed }"
                data-cursor-target
                @click="item.subscribed = !item.subscribed; onToggle(item)"
              >
                <span class="toggle-track">
                  <span class="toggle-thumb" />
                </span>
                <span class="toggle-text">{{ item.subscribed ? '已订阅' : '未订阅' }}</span>
              </button>
            </div>
          </GlassCard>
        </FadeContent>
      </div>
    </AnimatedContent>
  </div>
</template>

<style scoped>
.subscription { }

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-bottom: 1.5rem;
}
@media (max-width: 600px) {
  .stats-grid { grid-template-columns: 1fr; }
}

.loading-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
}
.empty-wrap { max-width: 480px; margin: 0 auto; }

.sub-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.sub-card {
  height: 100%;
  position: relative;
  transition: all 0.3s ease;
}
.sub-card.on {
  border-color: rgba(52, 211, 153, 0.35);
}
.sub-card.on::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--mint), transparent);
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.sub-head {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
}
.sub-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
}
.sub-icon.accent-sage  { color: var(--sage);  background: rgba(163, 230, 53, 0.08); }
.sub-icon.accent-teal  { color: var(--teal);  background: rgba(20, 184, 166, 0.08); }
.sub-icon.accent-mint  { color: var(--mint);  background: rgba(52, 211, 153, 0.08); }
.sub-icon.accent-amber { color: var(--amber); background: rgba(245, 158, 11, 0.08); }

.sub-label {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 600;
  font-size: 16px;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}
.sub-metric {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
  letter-spacing: 0.02em;
}
.sub-unit {
  margin-left: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 2px 10px;
  border-radius: 999px;
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.sub-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 16px;
}

.sub-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--glass-border);
}
.sub-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.sub-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
  font-family: 'DM Sans', sans-serif;
}
.toggle-track {
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: var(--glass-medium);
  border: 1px solid var(--glass-border);
  position: relative;
  transition: all 0.25s ease;
}
.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--text-tertiary);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.sub-toggle.on .toggle-track {
  background: rgba(132, 204, 22, 0.18);
  border-color: rgba(132, 204, 22, 0.30);
}
.sub-toggle.on .toggle-thumb {
  left: 20px;
  background: var(--mint);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.5);
}
.toggle-text {
  font-size: 12px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
  letter-spacing: 0.04em;
  min-width: 48px;
  text-align: right;
}
.sub-toggle.on .toggle-text {
  color: var(--mint);
}
</style>
