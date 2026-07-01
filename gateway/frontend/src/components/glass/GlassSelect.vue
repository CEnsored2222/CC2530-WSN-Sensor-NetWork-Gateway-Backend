<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue'
import Icon from '@/components/icons/Icon.vue'

const props = defineProps({
  modelValue: { type: [String, Number, null], default: null },
  options: { type: Array, default: () => [] }, // [{ value, label }]
  label: { type: String, default: '' },
  placeholder: { type: String, default: '请选择' },
  disabled: { type: Boolean, default: false }
})

defineEmits(['update:modelValue'])

function findLabel(val) {
  const opt = props.options.find((o) => o.value === val)
  return opt ? opt.label : ''
}

const buttonEl = ref(null)
const dropdownStyle = ref({})

function updateDropdownPos() {
  const el = buttonEl.value?.$el || buttonEl.value
  if (!el || !el.getBoundingClientRect) return
  const rect = el.getBoundingClientRect()
  dropdownStyle.value = {
    position: 'fixed',
    top: `${rect.bottom + 8}px`,
    left: `${rect.left}px`,
    width: `${rect.width}px`,
    zIndex: '9999'
  }
}

function onButtonClick() {
  updateDropdownPos()
}

function onScrollResize() {
  if (Object.keys(dropdownStyle.value).length) updateDropdownPos()
}

onMounted(() => {
  window.addEventListener('scroll', onScrollResize, true)
  window.addEventListener('resize', onScrollResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScrollResize, true)
  window.removeEventListener('resize', onScrollResize)
})
</script>

<template>
  <div class="w-full">
    <label v-if="label" class="block mb-1.5 text-sm font-medium" style="color: var(--text-secondary)">
      {{ label }}
    </label>
    <Listbox
      :model-value="modelValue"
      :disabled="disabled"
      @update:model-value="$emit('update:modelValue', $event)"
    >
      <div class="relative">
        <ListboxButton
          ref="buttonEl"
          class="glass-input w-full flex items-center justify-between text-left cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          @click="onButtonClick"
        >
          <span :class="!modelValue && modelValue !== 0 && 'text-tertiary'" :style="(!modelValue && modelValue !== 0) ? { color: 'var(--text-tertiary)' } : {}">
            {{ findLabel(modelValue) || placeholder }}
          </span>
          <Icon name="chevronDown" :size="16" class="shrink-0 ml-2 transition-transform ui-open:rotate-180" />
        </ListboxButton>

        <Teleport to="body">
          <Transition
            enter-active-class="transition duration-150 ease-out"
            enter-from-class="opacity-0 translate-y-1"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition duration-100 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 translate-y-1"
          >
            <ListboxOptions
              class="glass-select-dropdown rounded-xl py-1.5 max-h-60 overflow-auto focus:outline-none"
              :style="dropdownStyle"
            >
              <ListboxOption
                v-for="opt in options"
                :key="opt.value"
                :value="opt.value"
                v-slot="{ active, selected }"
                as="template"
              >
                <li
                  class="relative cursor-pointer select-none py-2 px-3.5 text-sm flex items-center justify-between rounded-lg mx-1.5 transition-colors"
                  :style="active ? { background: 'rgba(132, 204, 22, 0.15)', color: 'var(--text-primary)' } : { color: 'var(--text-secondary)' }"
                >
                  <span>{{ opt.label }}</span>
                  <Icon v-if="selected" name="check" :size="16" style="color: var(--color-accent)" />
                </li>
              </ListboxOption>
            </ListboxOptions>
          </Transition>
        </Teleport>
      </div>
    </Listbox>
  </div>
</template>

<style>
.glass-select-dropdown {
  background: rgba(10, 20, 16, 0.72);
  border: 1px solid rgba(132, 204, 22, 0.18);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.32), 0 0 0 1px rgba(255, 255, 255, 0.04);
}
[data-theme="light"] .glass-select-dropdown {
  background: rgba(244, 246, 244, 0.82);
}
</style>
