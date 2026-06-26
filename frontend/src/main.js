import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'
import { useThemeStore } from './stores/theme'
import './style.css'

const app = createApp(App)
const pinia = createPinia()
app.use(pinia)
// 在挂载前应用主题,避免首屏闪烁
useThemeStore(pinia)
app.use(router)
app.use(ElementPlus)
app.mount('#app')
