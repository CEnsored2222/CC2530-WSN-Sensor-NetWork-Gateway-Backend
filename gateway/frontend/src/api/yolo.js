// Yolo 推理服务直连 API 封装(链路 [1],不鉴权)
// 设计文档第 4.3 节:
//   GET  /health                健康检查
//   GET  /api/model_info        YOLO26 类别 + 人脸模型信息
//   POST /api/detect            目标检测(前端直连)
//   POST /api/recognize         人脸识别(前端直连,Yolo 内部拉人脸库)
//
// baseURL 动态设置:从 /api/vision/endpoint 拿到 yolo_url 后调 setYoloUrl()
import axios from 'axios'

// Yolo 服务地址(由 setYoloUrl 动态注入)
let yoloBase = ''

export const setYoloUrl = (url) => {
  yoloBase = (url || '').replace(/\/+$/, '')
}

export const getYoloUrl = () => yoloBase

const yolo = axios.create({
  baseURL: '',
  timeout: 15000
})

// 动态注入 baseURL(每次请求时取最新 yoloBase)
yolo.interceptors.request.use((cfg) => {
  cfg.baseURL = yoloBase
  return cfg
})

// 响应拦截:Yolo 直连不走 JWT,401 不跳登录;仅提示
yolo.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const msg = err.response?.data?.error || err.message || 'Yolo 服务请求失败'
    // 超时/网络错误:不弹消息(调用方需自行处理降级,避免逐帧弹窗)
    if (err.code === 'ECONNABORTED' || !err.response) {
      return Promise.reject(err)
    }
    console.error('[yolo]', msg)
    return Promise.reject(err)
  }
)

// pywebview 桌面环境辅助:检测桥接可用性
const hasPywebview = () => !!(window.pywebview && window.pywebview.api)

// 桥接结果统一处理:status===0 或 >=400 抛错,否则返回 data(与 axios 拦截器 res.data 语义一致)
function unwrapBridge(result, errMsg) {
  if (!result || result.status === 0 || result.status >= 400) {
    throw new Error((result && result.data && result.data.error) || errMsg)
  }
  return result.data
}

export const health = () => {
  // pywebview 模式下 file:// 无法直连 Yolo,推理实际走 Python 桥接,
  // 此处直接返回成功以放行 UI(yoloReady),真实连通性由 detect/recognize 体现
  if (hasPywebview()) return Promise.resolve({ status: 'ok' })
  return yolo.get('/health')
}

export const modelInfo = () => {
  if (hasPywebview()) return Promise.resolve({})
  return yolo.get('/api/model_info')
}

export const detectFrame = async (data) => {
  if (hasPywebview()) {
    // 走 Python 侧 vision_detect(frame_b64, options)
    const result = await window.pywebview.api.vision_detect(data.frame, { conf: data.conf })
    return unwrapBridge(result, 'Yolo 检测失败')
  }
  return yolo.post('/api/detect', data)
}

export const recognizeFrame = async (data) => {
  if (hasPywebview()) {
    // 走 Python 侧 vision_recognize(frame_b64, user_id)
    const result = await window.pywebview.api.vision_recognize(data.frame, data.user_id)
    return unwrapBridge(result, 'Yolo 识别失败')
  }
  return yolo.post('/api/recognize', data)
}

// 人脸特征提取(仅 pywebview 桥接暴露,Web 模式回退到 yolo 直连)
export const faceEmbed = async (frame) => {
  if (hasPywebview()) {
    const result = await window.pywebview.api.vision_face_embed(frame)
    return unwrapBridge(result, '人脸特征提取失败')
  }
  return yolo.post('/api/face_embed', { frame })
}

// ============ 桌面环境专用功能(存根) ============
// 以下函数仅在 pywebview EXE 环境下生效，浏览器下所有调用方均已通过
// isDesktop() 守卫提前返回，此处仅提供存根以通过编译。
// 如需查看桥接实现,请参考 gateway/http_proxy.py 与 gateway/gui_web.py 中
// 对应的 Python 端方法。

const _desktopGuard = async () => {
  if (!hasPywebview()) {
    throw new Error('该功能仅桌面端可用')
  }
}

export const getYoloSettings = async () => {
  await _desktopGuard()
  return window.pywebview.api.get_config()
}

export const saveYoloSettings = async (settings) => {
  await _desktopGuard()
  return window.pywebview.api.save_yolo_settings(settings)
}

export const downloadModel = async (modelName) => {
  await _desktopGuard()
  return window.pywebview.api.download_model(modelName)
}

export const installGpuLib = async () => {
  await _desktopGuard()
  return window.pywebview.api.install_gpu_lib()
}

export const installInsightfaceLib = async () => {
  await _desktopGuard()
  return window.pywebview.api.install_insightface()
}

export const installAllDependencies = async (mode) => {
  await _desktopGuard()
  return window.pywebview.api.install_all_deps(mode)
}

export const selectModelsDir = async () => {
  await _desktopGuard()
  return window.pywebview.api.select_models_dir()
}

export const startYoloService = async () => {
  await _desktopGuard()
  return window.pywebview.api.start_yolo_service()
}

export const stopYoloService = async () => {
  await _desktopGuard()
  return window.pywebview.api.stop_yolo_service()
}

export const getYoloServiceStatus = async () => {
  await _desktopGuard()
  return window.pywebview.api.get_yolo_service_status()
}

export const selectDataDir = async () => {
  await _desktopGuard()
  return window.pywebview.api.select_data_dir()
}
