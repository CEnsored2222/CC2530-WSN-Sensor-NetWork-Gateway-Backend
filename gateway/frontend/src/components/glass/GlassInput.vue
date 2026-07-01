<script setup>
import { computed, useAttrs } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: { type: [String, Number], default: '' },
  type: { type: String, default: 'text' },
  label: { type: String, default: '' },
  error: { type: String, default: '' },
  hint: { type: String, default: '' },
  iconLeft: { type: String, default: '' }
})

defineEmits(['update:modelValue'])

const attrs = useAttrs()

const inputClasses = computed(() => [
  'glass-input',
  props.iconLeft && 'pl-10',
  props.error && 'border-semantic-danger/50 focus:border-semantic-danger focus:shadow-none'
])
</script>

<template>
  <div class="w-full">
    <label v-if="label" class="block mb-1.5 text-sm font-medium" style="color: var(--text-secondary)">
      {{ label }}
    </label>
    <div class="relative">
      <span v-if="iconLeft" class="absolute left-3 top-1/2 -translate-y-1/2" style="color: var(--text-tertiary)">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
        </svg>
      </span>
      <input
        v-bind="attrs"
        :type="type"
        :value="modelValue"
        :class="inputClasses"
        @input="$emit('update:modelValue', $event.target.value)"
      />
    </div>
    <p v-if="error" class="mt-1.5 text-xs" style="color: var(--color-danger)">{{ error }}</p>
    <p v-else-if="hint" class="mt-1.5 text-xs" style="color: var(--text-tertiary)">{{ hint }}</p>
  </div>
</template>
