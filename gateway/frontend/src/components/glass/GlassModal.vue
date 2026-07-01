<script setup>
import { Dialog, DialogPanel, DialogTitle, TransitionRoot, TransitionChild } from '@headlessui/vue'
import Icon from '@/components/icons/Icon.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: '' },
  size: { type: String, default: 'md' } // 'sm' | 'md' | 'lg' | 'xl'
})

defineEmits(['update:modelValue', 'close'])

const sizeMap = {
  sm: 'max-w-md',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
  xl: 'max-w-4xl'
}

function close() {
  // @vueuse/motion 或 headlessui 处理过渡后触发
}
</script>

<template>
  <TransitionRoot appear :show="modelValue" as="template">
    <Dialog @close="$emit('update:modelValue', false)" class="relative z-[9999]">
      <TransitionChild
        as="template"
        enter="duration-300 ease-out"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="duration-200 ease-in"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/50 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 flex items-center justify-center p-4">
        <TransitionChild
          as="template"
          enter="duration-300 ease-out"
          enter-from="opacity-0 scale-96 translate-y-4"
          enter-to="opacity-100 scale-100 translate-y-0"
          leave="duration-200 ease-in"
          leave-from="opacity-100 scale-100 translate-y-0"
          leave-to="opacity-0 scale-96 translate-y-4"
        >
          <DialogPanel
            class="glass-heavy w-full rounded-2xl p-6 shadow-2xl"
            :class="sizeMap[size]"
            style="box-shadow: 0 24px 64px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.12);"
          >
            <div v-if="title" class="flex items-center justify-between mb-5">
              <DialogTitle class="text-lg font-semibold font-display" style="color: var(--text-primary)">
                {{ title }}
              </DialogTitle>
              <button
                class="w-8 h-8 rounded-lg flex items-center justify-center cursor-pointer transition-colors"
                style="color: var(--text-tertiary)"
                @click="$emit('update:modelValue', false)"
              >
                <Icon name="close" :size="18" />
              </button>
            </div>
            <slot />
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
