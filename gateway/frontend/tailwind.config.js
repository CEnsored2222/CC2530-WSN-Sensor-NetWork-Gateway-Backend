/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        aurora: {
          sage: '#84cc16',
          'sage-deep': '#65a30d',
          'sage-soft': '#a3e635',
          teal: '#14b8a6',
          'teal-deep': '#0d9488',
          mint: '#34d399',
          emerald: '#10b981',
          lime: '#a3e635',
          spring: '#a7f3d0',
          amber: '#f59e0b'
        },
        glass: {
          light: 'rgba(255,255,255,0.03)',
          medium: 'rgba(255,255,255,0.06)',
          heavy: 'rgba(255,255,255,0.09)'
        },
        semantic: {
          success: '#34d399',
          warning: '#f59e0b',
          danger: '#f87171',
          info: '#14b8a6',
          critical: '#f59e0b'
        },
        base: {
          DEFAULT: '#060d0a',
          deep: '#0a1410',
          mid: '#0f1a14'
        }
      },
      fontFamily: {
        display: ['"Roboto Flex"', '"DM Sans"', '"PingFang SC"', 'sans-serif'],
        body: ['"DM Sans"', '-apple-system', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace']
      },
      borderRadius: {
        sm: '8px',
        md: '12px',
        lg: '16px',
        xl: '24px',
        '2xl': '32px'
      },
      backdropBlur: {
        glass: '20px',
        'glass-heavy': '28px'
      },
      boxShadow: {
        glass: '0 8px 32px rgba(0,0,0,0.20), inset 0 1px 0 rgba(255,255,255,0.08)',
        'glass-hover': '0 12px 40px rgba(0,0,0,0.24), 0 0 32px rgba(52,211,153,0.06), inset 0 1px 0 rgba(255,255,255,0.10)',
        glow: '0 0 40px rgba(52,211,153,0.15)'
      },
      transitionTimingFunction: {
        expo: 'cubic-bezier(0.16, 1, 0.3, 1)',
        'out-soft': 'cubic-bezier(0.4, 0, 0.2, 1)'
      },
      keyframes: {
        'aurora-float': {
          '0%, 100%': { transform: 'translate(0, 0) scale(1)' },
          '33%': { transform: 'translate(60px, -40px) scale(1.1)' },
          '66%': { transform: 'translate(-40px, 60px) scale(0.95)' }
        },
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' }
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.8)', opacity: '0.8' },
          '100%': { transform: 'scale(2)', opacity: '0' }
        }
      },
      animation: {
        'aurora-float': 'aurora-float 20s ease-in-out infinite',
        shimmer: 'shimmer 2s linear infinite',
        'pulse-ring': 'pulse-ring 1.5s cubic-bezier(0.4,0,0.6,1) infinite'
      }
    }
  },
  plugins: []
}
