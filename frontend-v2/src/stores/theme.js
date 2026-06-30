import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

/**
 * 主题 Store
 * 保留 toggle/apply/localStorage/theme-change 事件机制不变
 * CSS 变量集通过 [data-theme] 属性选择器在 main.css 中定义
 */
export const useThemeStore = defineStore('theme', () => {
  const stored = typeof localStorage !== 'undefined' && localStorage.getItem('atmos_theme')
  const theme = ref(stored || 'dark') // 'dark' | 'light'

  function apply(t) {
    document.documentElement.setAttribute('data-theme', t)
  }

  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  watch(theme, (t) => {
    apply(t)
    try { localStorage.setItem('atmos_theme', t) } catch (e) {}
    // 通知图表等需要重绘的组件
    window.dispatchEvent(new CustomEvent('theme-change', { detail: t }))
  }, { immediate: true })

  return { theme, toggle, apply }
})
