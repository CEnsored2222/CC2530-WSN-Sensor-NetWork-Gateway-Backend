<script setup>
import { ref } from 'vue'
import GlassCard from '@/components/glass/GlassCard.vue'
import CountUp from '@/components/vuebits/CountUp.vue'
import Icon from '@/components/icons/Icon.vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: Number, required: true },
  unit: { type: String, default: '' },
  decimals: { type: Number, default: 0 },
  eyebrow: { type: String, default: '' },
  icon: { type: String, default: '' },
  accent: { type: String, default: 'mint' }, // mint | sage | teal | amber | danger
  trend: { type: [Number, String], default: null },
  trendLabel: { type: String, default: '较上次' },
  loaded: { type: Boolean, default: true }
})

const accentMap = {
  mint:   { color: 'var(--mint)', glow: 'rgba(52,211,153,0.18)' },
  sage:   { color: 'var(--sage)', glow: 'rgba(132,204,22,0.18)' },
  teal:   { color: 'var(--teal)', glow: 'rgba(20,184,166,0.18)' },
  amber:  { color: 'var(--amber)', glow: 'rgba(245,158,11,0.18)' },
  danger: { color: 'var(--color-danger)', glow: 'rgba(248,113,113,0.18)' }
}

const counter = ref(null)

function update(newVal) {
  counter.value?.update(newVal)
}
defineExpose({ update })
</script>

<template>
  <GlassCard padding="p-6" class="glass-stat sheen-on-hover">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <p v-if="eyebrow" class="eyebrow mb-2">{{ eyebrow }}</p>
        <p class="text-sm glass-stat__label">{{ label }}</p>
        <div class="mt-2 flex items-baseline gap-1.5">
          <CountUp
            v-if="loaded"
            ref="counter"
            :to="props.value"
            :decimals="decimals"
            class="glass-stat__value"
            :style="{ color: accentMap[accent].color }"
          />
          <span v-else class="glass-stat__value glass-stat__placeholder" :style="{ color: accentMap[accent].color }">—</span>
          <span v-if="unit" class="text-base glass-stat__unit">{{ unit }}</span>
        </div>
        <p v-if="trend !== null && trend !== ''" class="mt-2 text-xs glass-stat__trend">
          {{ trendLabel }}
          <span :class="String(trend).startsWith('-') ? 'glass-stat__trend--down' : 'glass-stat__trend--up'">
            {{ trend }}
          </span>
        </p>
      </div>
      <div
        v-if="icon"
        class="glass-stat__icon"
        :style="{ background: accentMap[accent].glow, color: accentMap[accent].color }"
      >
        <Icon :name="icon" :size="22" />
      </div>
    </div>
  </GlassCard>
</template>

<style scoped>
.glass-stat__label {
  color: var(--text-tertiary);
  font-weight: 500;
}
.glass-stat__value {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 700;
  font-size: 2rem;
  letter-spacing: -0.03em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.glass-stat__placeholder {
  opacity: 0.3;
}
.glass-stat__unit {
  color: var(--text-tertiary);
  font-weight: 500;
}
.glass-stat__trend {
  color: var(--text-tertiary);
}
.glass-stat__trend--up { color: var(--mint); }
.glass-stat__trend--down { color: var(--color-danger); }
.glass-stat__icon {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
</style>
