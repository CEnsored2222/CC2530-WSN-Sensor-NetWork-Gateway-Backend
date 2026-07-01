import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  // pywebview 以 file:// 协议加载 dist/index.html,资源必须用相对路径
  base: './',
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    // 桌面应用构建产物输出到 dist/,由 pywebview 加载
    outDir: './dist',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('gsap')) return 'gsap'
            if (id.includes('echarts') || id.includes('zrender')) return 'echarts'
            if (id.includes('vue') || id.includes('pinia')) return 'vendor'
          }
        }
      }
    }
  },
  server: {
    host: '0.0.0.0',
    port: 5173
    // 桌面应用通过 pywebview js_api 桥接,不需要 dev server proxy
    // (Web 部署模式如需代理可在此处恢复 proxy 配置)
  }
})
