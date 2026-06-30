import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useThemeStore = defineStore('theme', () => {
  const stored = typeof localStorage !== 'undefined' && localStorage.getItem('atmos_theme')
  const theme = ref(stored || 'dark') // 'dark' | 'light'

  function apply(t) {
    document.documentElement.setAttribute('data-theme', t)
  }

  function toggle(event) {
    // 主题切换:优先用 View Transitions API 做圆形展开过渡,无支持时直接切换
    const setTheme = () => {
      theme.value = theme.value === 'dark' ? 'light' : 'dark'
    }
    if (typeof document !== 'undefined' && document.startViewTransition) {
      const x = event?.clientX ?? window.innerWidth / 2
      const y = event?.clientY ?? 0
      document.documentElement.style.setProperty('--theme-x', x + 'px')
      document.documentElement.style.setProperty('--theme-y', y + 'px')
      document.startViewTransition(() => setTheme())
    } else {
      setTheme()
    }
  }

  watch(theme, (t) => {
    apply(t)
    try { localStorage.setItem('atmos_theme', t) } catch (e) {}
    // 通知图表等需要重绘的组件
    window.dispatchEvent(new CustomEvent('theme-change', { detail: t }))
  }, { immediate: true })

  return { theme, toggle, apply }
})
