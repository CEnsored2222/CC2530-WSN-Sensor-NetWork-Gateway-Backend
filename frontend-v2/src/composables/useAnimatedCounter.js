import { ref, onMounted, watch } from 'vue'
import { gsap } from 'gsap'

/**
 * 数字滚动动画 composable
 * 用法:
 *   const count = useAnimatedCounter(() => props.value, { duration: 1.2 })
 *   <span>{{ count.display }}</span>
 */
export function useAnimatedCounter(source, options = {}) {
  const { duration = 1.2, ease = 'power2.out', decimals = 1, suffix = '', prefix = '' } = options
  const display = ref(`${prefix}0${suffix}`)
  const obj = { val: 0 }

  function animate(to) {
    gsap.to(obj, {
      val: Number(to) || 0,
      duration,
      ease,
      onUpdate: () => {
        display.value = `${prefix}${obj.val.toFixed(decimals)}${suffix}`
      }
    })
  }

  onMounted(() => animate(typeof source === 'function' ? source() : source))
  watch(
    () => (typeof source === 'function' ? source() : source),
    (newVal) => animate(newVal)
  )

  return { display }
}
