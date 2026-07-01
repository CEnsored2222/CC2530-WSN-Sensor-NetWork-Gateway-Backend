<script setup>
import { TransitionRoot, TransitionChild, Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import Icon from '@/components/icons/Icon.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  side: { type: String, default: 'right' }, // 'right' | 'left'
  width: { type: String, default: '460px' }
})

defineEmits(['update:modelValue'])
</script>

<template>
  <TransitionRoot appear :show="modelValue" as="template">
    <Dialog @close="$emit('update:modelValue', false)" class="fixed inset-0 z-[9999]">
      <TransitionChild
        as="template"
        enter="duration-300 ease-out"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="duration-200 ease-in"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/55 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full" :class="side === 'left' ? 'justify-start' : 'justify-end'">
          <TransitionChild
            as="template"
            enter="transition duration-300 ease-out"
            :enter-from="side === 'right' ? 'translate-x-full' : '-translate-x-full'"
            enter-to="translate-x-0"
            leave="transition duration-200 ease-in"
            :leave-from="'translate-x-0'"
            :leave-to="side === 'right' ? 'translate-x-full' : '-translate-x-full'"
          >
            <DialogPanel
              class="glass-heavy h-full flex flex-col shadow-2xl"
              :class="side === 'right' ? 'rounded-l-2xl' : 'rounded-r-2xl'"
              :style="{ width, maxWidth: '92vw', borderLeft: side === 'right' ? '1px solid var(--glass-border)' : 'none', borderRight: side === 'left' ? '1px solid var(--glass-border)' : 'none' }"
            >
              <div class="flex items-start justify-between px-6 pt-6 pb-4 border-b" style="border-color: var(--glass-border)">
                <div class="min-w-0">
                  <DialogTitle v-if="title" class="text-lg font-display font-semibold truncate" style="color: var(--text-primary)">
                    {{ title }}
                  </DialogTitle>
                  <p v-if="subtitle" class="mt-1 text-xs" style="color: var(--text-tertiary); font-family: 'DM Sans', sans-serif; letter-spacing: 0.04em;">
                    {{ subtitle }}
                  </p>
                </div>
                <button
                  class="shrink-0 ml-3 w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer transition-colors hover:bg-white/5"
                  style="color: var(--text-tertiary)"
                  data-cursor-target
                  @click="$emit('update:modelValue', false)"
                >
                  <Icon name="close" :size="18" />
                </button>
              </div>
              <div class="flex-1 overflow-y-auto px-6 py-5">
                <slot />
              </div>
              <div v-if="$slots.footer" class="px-6 py-4 border-t" style="border-color: var(--glass-border)">
                <slot name="footer" />
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
