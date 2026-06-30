import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * UI Store: 侧边栏状态、全局加载态、通知队列
 */
export const useUiStore = defineStore('ui', () => {
  const sidebarCollapsed = ref(false)
  const globalLoading = ref(false)
  const toasts = ref([])
  let toastId = 0

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function setSidebar(collapsed) {
    sidebarCollapsed.value = collapsed
  }

  function setLoading(v) {
    globalLoading.value = v
  }

  /**
   * @param {object} opts { type: 'success'|'warning'|'danger'|'info', title, message, duration }
   */
  function pushToast(opts) {
    const id = ++toastId
    const toast = {
      id,
      type: opts.type || 'info',
      title: opts.title || '',
      message: opts.message || '',
      duration: opts.duration ?? 3500
    }
    toasts.value.push(toast)
    if (toast.duration > 0) {
      setTimeout(() => dismissToast(id), toast.duration)
    }
    return id
  }

  function dismissToast(id) {
    const idx = toasts.value.findIndex((t) => t.id === id)
    if (idx > -1) toasts.value.splice(idx, 1)
  }

  return {
    sidebarCollapsed,
    globalLoading,
    toasts,
    toggleSidebar,
    setSidebar,
    setLoading,
    pushToast,
    dismissToast
  }
})
