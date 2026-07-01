<script setup>
import { TabGroup, TabList, Tab, TabPanels, TabPanel } from '@headlessui/vue'

defineProps({
  tabs: { type: Array, default: () => [] } // [{ name, label }]
})

const modelValue = defineModel({ type: Number, default: 0 })
</script>

<template>
  <TabGroup :selected-index="modelValue" @change="modelValue = $event">
    <TabList class="flex items-center gap-1 p-1 glass-light rounded-xl">
      <Tab
        v-for="tab in tabs"
        :key="tab.name"
        v-slot="{ selected }"
        as="template"
      >
        <button
          class="relative px-4 py-2 text-sm font-medium rounded-lg transition-all cursor-pointer"
          :style="selected
            ? { color: 'var(--mint)', background: 'rgba(132, 204, 22, 0.10)', boxShadow: 'inset 0 0 0 1px rgba(132, 204, 22, 0.18)' }
            : { color: 'var(--text-tertiary)' }"
        >
          {{ tab.label }}
          <span
            v-if="selected"
            class="absolute inset-x-3 -bottom-px h-0.5 rounded-full"
            style="background: var(--mint)"
          />
        </button>
      </Tab>
    </TabList>
    <TabPanels class="mt-5">
      <TabPanel v-for="tab in tabs" :key="tab.name">
        <slot :name="tab.name" />
      </TabPanel>
    </TabPanels>
  </TabGroup>
</template>
