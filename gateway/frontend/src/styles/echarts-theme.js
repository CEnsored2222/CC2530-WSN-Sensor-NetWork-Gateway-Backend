/**
 * ECharts 玻璃拟态极光主题
 * 适配暗色/亮色双主题,通过 CSS 变量读取色彩
 */

export function getAuroraTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
  return {
    backgroundColor: 'transparent',
    textStyle: {
      fontFamily: 'IBM Plex Sans, -apple-system, sans-serif',
      color: isDark ? 'rgba(255,255,255,0.7)' : 'rgba(20,20,40,0.7)'
    },
    title: {
      textStyle: {
        fontFamily: 'Syne, sans-serif',
        color: isDark ? 'rgba(255,255,255,0.95)' : 'rgba(20,20,40,0.95)',
        fontWeight: 600
      }
    },
    legend: {
      textStyle: {
        color: isDark ? 'rgba(255,255,255,0.6)' : 'rgba(20,20,40,0.6)'
      },
      pageTextStyle: {
        color: isDark ? 'rgba(255,255,255,0.6)' : 'rgba(20,20,40,0.6)'
      }
    },
    tooltip: {
      backgroundColor: isDark ? 'rgba(15,15,35,0.85)' : 'rgba(255,255,255,0.85)',
      borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)',
      borderWidth: 1,
      padding: [10, 14],
      textStyle: {
        color: isDark ? 'rgba(255,255,255,0.9)' : 'rgba(20,20,40,0.9)',
        fontSize: 13
      },
      extraCssText: 'backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.3);'
    },
    grid: {
      top: 40,
      right: 24,
      bottom: 40,
      left: 48,
      containLabel: true
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)' } },
      axisTick: { lineStyle: { color: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)' } },
      axisLabel: { color: isDark ? 'rgba(255,255,255,0.5)' : 'rgba(20,20,40,0.5)' },
      splitLine: { show: false }
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: isDark ? 'rgba(255,255,255,0.5)' : 'rgba(20,20,40,0.5)' },
      splitLine: {
        lineStyle: {
          color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
          type: 'dashed'
        }
      }
    },
    color: ['#84cc16', '#34d399', '#14b8a6', '#a7f3d0', '#5eead4', '#86efac', '#fbbf24'],
    line: {
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { width: 2.5 },
      itemStyle: {
        borderWidth: 2,
        borderColor: isDark ? '#0a0a1a' : '#fff'
      },
      areaStyle: {
        opacity: 0.15
      },
      emphasis: {
        focus: 'series',
        scale: 1.4
      }
    },
    bar: {
      itemStyle: {
        borderRadius: [6, 6, 0, 0]
      },
      emphasis: {
        itemStyle: {
          shadowBlur: 20,
          shadowColor: 'rgba(52, 211, 153, 0.4)'
        }
      }
    },
    pie: {
      itemStyle: {
        borderColor: isDark ? '#0a0a1a' : '#fff',
        borderWidth: 3
      },
      emphasis: {
        scaleSize: 8
      }
    },
    radar: {
      symbol: 'circle',
      symbolSize: 5,
      lineStyle: { width: 2 }
    }
  }
}

/**
 * 注册主题切换监听:主题变更时返回新主题
 */
export function watchThemeChange(callback) {
  const handler = () => callback(getAuroraTheme())
  window.addEventListener('theme-change', handler)
  return () => window.removeEventListener('theme-change', handler)
}
