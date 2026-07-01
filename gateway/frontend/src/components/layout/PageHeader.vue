<script setup>
import ShuffleText from '@/components/vuebits/ShuffleText.vue'
import RotatingText from '@/components/vuebits/RotatingText.vue'

defineProps({
  title: { type: String, required: true },
  eyebrow: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  rotatingWords: { type: Array, default: null },
  align: { type: String, default: 'left' }
})
</script>

<template>
  <header class="page-header" :class="`page-header--${align}`">
    <p v-if="eyebrow" class="eyebrow page-header__eyebrow">
      <span class="eyebrow-dot" />{{ eyebrow }}
    </p>
    <ShuffleText
      :text="title"
      tag="h2"
      class="page-header__title"
      :trigger-on-hover="false"
      :loop="true"
      :loop-delay="8"
    />
    <RotatingText
      v-if="rotatingWords && rotatingWords.length"
      :words="rotatingWords"
      class="page-header__subtitle"
    />
    <p v-else-if="subtitle" class="page-header__subtitle page-header__subtitle--static">
      {{ subtitle }}
    </p>
    <slot name="extra" />
  </header>
</template>

<style scoped>
.page-header {
  margin-bottom: 2rem;
}
.page-header--center {
  text-align: center;
}
.page-header__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.eyebrow-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--mint);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.7);
}
.page-header__title {
  font-family: 'Roboto Flex', sans-serif;
  font-variation-settings: 'wght' 700, 'wdth' 105;
  font-size: clamp(1.875rem, 3vw, 2.75rem);
  letter-spacing: -0.03em;
  line-height: 1.05;
  color: var(--text-primary);
  display: block;
}
.page-header__subtitle {
  margin-top: 10px;
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
  letter-spacing: 0.08em;
  color: var(--mint);
  text-transform: uppercase;
  display: inline-block;
  min-height: 1.2em;
}
.page-header__subtitle--static {
  color: var(--text-tertiary);
  text-transform: none;
  letter-spacing: 0;
  font-family: 'DM Sans', sans-serif;
  font-size: 14px;
}
</style>
