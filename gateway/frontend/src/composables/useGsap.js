import { onMounted, onBeforeUnmount } from 'vue'
import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

/**
 * GSAP 动画辅助 composable
 * 提供 Timeline 创建和 ScrollTrigger 封装
 */
export function useGsap() {
  function timeline(options = {}) {
    return gsap.timeline(options)
  }

  function staggerEnter(elements, options = {}) {
    const {
      y = 24,
      opacity = 0,
      duration = 0.5,
      stagger = 0.08,
      ease = 'expo.out',
      delay = 0
    } = options
    return gsap.fromTo(
      elements,
      { y, opacity },
      { y: 0, opacity: 1, duration, stagger, ease, delay }
    )
  }

  function scrollReveal(elements, options = {}) {
    const {
      y = 40,
      opacity = 0,
      duration = 0.6,
      stagger = 0.1,
      ease = 'expo.out',
      start = 'top 85%'
    } = options
    return gsap.fromTo(
      elements,
      { y, opacity },
      {
        y: 0,
        opacity: 1,
        duration,
        stagger,
        ease,
        scrollTrigger: {
          trigger: elements[0] || elements,
          start
        }
      }
    )
  }

  return { gsap, timeline, staggerEnter, scrollReveal, ScrollTrigger }
}
