// Yolo 推理服务直连 API 封装(链路 [1],不鉴权)
// 设计文档第 4.3 节:
//   GET  /health                健康检查
//   GET  /api/model_info        YOLO26 类别 + 人脸模型信息
//   POST /api/detect            目标检测(前端直连)
//   POST /api/recognize         人脸识别(前端直连,Yolo 内部拉人脸库)
//
// baseURL 动态设置:从 /api/vision/endpoint 拿到 yolo_url 后调 setYoloUrl()
import axios from 'axios'
import { ElMessage } from 'element-plus'

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
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

export const health = () => yolo.get('/health')

export const modelInfo = () => yolo.get('/api/model_info')

export const detectFrame = (data) => yolo.post('/api/detect', data)

export const recognizeFrame = (data) => yolo.post('/api/recognize', data)
