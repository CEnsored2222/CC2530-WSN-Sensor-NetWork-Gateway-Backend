<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { getEndpoint, listFaces, addFace, removeFace } from '@/api/vision'
import {
  setYoloUrl, health as yoloHealth, detectFrame, recognizeFrame,
  getYoloSettings, saveYoloSettings, downloadModel,
  installGpuLib, installInsightfaceLib, installAllDependencies,
  selectModelsDir, startYoloService, stopYoloService, getYoloServiceStatus,
  selectDataDir
} from '@/api/yolo'
import Icon from '@/components/icons/Icon.vue'
import GlassModal from '@/components/glass/GlassModal.vue'
import PageHeader from '@/components/layout/PageHeader.vue'

const userStore = useUserStore()
const ui = useUiStore()

// 类别配色板(与 Ultralytics res.plot() 风格一致,不同类别不同颜色)
const CLASS_COLORS = [
  '#FF3838', '#FF9D97', '#FF701F', '#FFB21D', '#CFD23B',
  '#37F47C', '#6AE2C7', '#51A9FF', '#A1C6FF', '#FFB6C1',
  '#FFA07A', '#FF7F50', '#FFD700', '#ADFF2F', '#7FFFD4',
  '#87CEEB', '#DDA0DD', '#FF69B4', '#FF1493', '#F2F6FC',
]

const mode = ref('detect')
const running = ref(false)
const yoloReady = ref(false)
const yoloUrl = ref('')
const conf = ref(0.35)
const fps = ref(0)
const detections = ref([])
const faces = ref([])
const errorMsg = ref('')
const faceLibrary = ref([])
const faceDialogVisible = ref(false)
const registerName = ref('')
const registerLoading = ref(false)
const capturing = ref(false)
// Yolo 推理连续失败计数(达到阈值后提示用户检查服务,但不强制关闭摄像头)
const failCount = ref(0)
const INFERENCE_FAIL_THRESHOLD = 5

// ============ Yolo 设置面板 ============
const settingsVisible = ref(false)
const settingsLoading = ref(false)
const settingsSaving = ref(false)
const yoloSettings = ref({
  yolo_service_url: 'http://127.0.0.1:6001',
  yolo_enabled: true,
  yolo_device: '',
  yolo_imgsz: 480,
  face_model: 'buffalo_m',
  gpu: { gpu_available: false, device_count: 0, devices: [], error: '' },
  dependencies: {},
  models: []
})
const pipLog = ref('')
const pipRunning = ref(false)
const pipRunningPackage = ref('')
const downloadingModel = ref('')
const downloadingProgress = ref({}) // {modelName: {downloaded, total, percent}}

// 模型存储目录(由 config.MODELS_DIR 提供,空时使用默认值)
const modelsDir = ref('')

// 数据存储根目录(Python 运行时、模型、配置文件统一存放目录)
const dataDir = ref('')
const selectingDataDir = ref(false)

// Yolo 服务子进程状态
const yoloServiceRunning = ref(false)
const yoloServicePid = ref(null)
const yoloServiceStarting = ref(false)
const yoloServiceStopping = ref(false)
const yoloServiceLog = ref('')
let yoloServicePollTimer = null

// 模型显示名映射
const MODEL_LABELS = {
  insightface_buffalo_l: 'Buffalo L 人脸模型 (insightface, GPU 推荐)',
  insightface_buffalo_m: 'Buffalo M 人脸模型 (insightface, CPU/GPU 通用)',
  yolo26n: 'Yolo 目标检测模型 (yolo26n.pt)'
}

const videoRef = ref(null)
const canvasRef = ref(null)
const drawCanvasRef = ref(null)
let stream = null
let frameTimer = null
let frameTimes = []

const userId = computed(() => userStore.user?.id)
const hasFaces = computed(() => faceLibrary.value.length > 0)
const isDesktop = computed(() => !!(window.pywebview && window.pywebview.api))

// 注册 pywebview 桥接回调(进度推送)
// 使用函数封装,确保 onMounted 和 pywebviewready 事件都能触发注册
function registerPywebviewCallbacks() {
  if (!window.pywebview) return
  // pip 安装进度回调
  window.__pipInstallProgress = (pkg, line) => {
    pipLog.value += line
  }
  // 模型下载进度回调(由 Python 侧 evaluate_js 推送)
  // percent 约定:-1=已开始(总大小未知),-2=失败,0~100=正常进度
  window.__modelDownloadProgress = (modelName, downloaded, total, percent) => {
    // 实时记录进度,供进度条展示
    downloadingProgress.value = {
      ...downloadingProgress.value,
      [modelName]: { downloaded, total, percent }
    }
    // 异步下载完成/失败事件处理(Python 侧 download_model 在线程中执行)
    if (percent === -2) {
      // 下载失败:推送错误 toast,清空下载中状态,刷新设置
      ui.pushToast({
        type: 'danger',
        title: '下载失败',
        message: MODEL_LABELS[modelName] || modelName
      })
      if (downloadingModel.value === modelName) downloadingModel.value = ''
      refreshSettings()
    } else if (percent >= 100) {
      // 下载完成:推送成功 toast,清空下载中状态,刷新设置
      ui.pushToast({
        type: 'success',
        title: '下载完成',
        message: MODEL_LABELS[modelName] || modelName
      })
      if (downloadingModel.value === modelName) downloadingModel.value = ''
      refreshSettings()
    }
  }
  // Yolo 服务子进程日志
  window.__yoloServiceLog = (line) => {
    yoloServiceLog.value += line
  }
}

onMounted(async () => {
  // 注册回调:立即注册一次(若 pywebview 已就绪),并监听 pywebviewready 事件兜底
  registerPywebviewCallbacks()
  window.addEventListener('pywebviewready', registerPywebviewCallbacks)
  await initEndpoint()
  await loadFaceLibrary()
})

onUnmounted(() => {
  stopCamera()
  stopYoloServicePolling()
  window.removeEventListener('pywebviewready', registerPywebviewCallbacks)
  if (window.__pipInstallProgress) delete window.__pipInstallProgress
  if (window.__modelDownloadProgress) delete window.__modelDownloadProgress
  if (window.__yoloServiceLog) delete window.__yoloServiceLog
})

async function initEndpoint() {
  // 桌面端(pywebview):通过 HTTP 代理连接 Yolo 服务
  if (isDesktop.value) {
    try {
      const settings = await getYoloSettings()
      if (settings) {
        yoloUrl.value = settings.yolo_service_url || 'http://127.0.0.1:6001'
        setYoloUrl(yoloUrl.value)
        yoloSettings.value = settings
      } else {
        yoloUrl.value = 'http://127.0.0.1:6001'
        setYoloUrl(yoloUrl.value)
      }
    } catch {
      yoloUrl.value = 'http://127.0.0.1:6001'
      setYoloUrl(yoloUrl.value)
    }
    // 实际健康检查:通过 HTTP 代理 ping Yolo 服务
    try {
      await yoloHealth()
      yoloReady.value = true
    } catch {
      yoloReady.value = false
      ui.pushToast({ type: 'warning', title: 'Yolo 服务未连接', message: '请在设置中启动 Yolo 服务' })
    }
    return
  }

  // Web 模式:从云端后端获取 Yolo 服务地址
  try {
    const res = await getEndpoint()
    const url = res?.yolo_url || ''
    yoloUrl.value = url
    setYoloUrl(url)
    if (url) {
      try {
        await yoloHealth()
        yoloReady.value = true
      } catch {
        yoloReady.value = false
        ui.pushToast({ type: 'warning', title: 'Yolo 视觉服务离线,请联系管理员' })
      }
    } else {
      yoloReady.value = false
    }
  } catch {
    yoloReady.value = false
  }
}

async function loadFaceLibrary() {
  try {
    faceLibrary.value = await listFaces()
  } catch {
    faceLibrary.value = []
  }
}

async function startCamera() {
  if (!yoloReady.value) {
    ui.pushToast({ type: 'warning', title: 'Yolo 视觉服务离线,无法启动推理' })
    return
  }
  errorMsg.value = ''
  failCount.value = 0
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' },
      audio: false
    })
    videoRef.value.srcObject = stream
    await videoRef.value.play()
    running.value = true
    frameTimes = []
    loop()
  } catch (e) {
    errorMsg.value = '摄像头开启失败:' + (e.message || '请检查浏览器权限')
    ui.pushToast({ type: 'danger', title: '摄像头开启失败', message: e.message || '请检查浏览器权限' })
  }
}

function stopCamera() {
  running.value = false
  if (frameTimer) {
    clearTimeout(frameTimer)
    frameTimer = null
  }
  if (stream) {
    stream.getTracks().forEach((t) => t.stop())
    stream = null
  }
  if (videoRef.value) {
    videoRef.value.srcObject = null
  }
  detections.value = []
  faces.value = []
  fps.value = 0
  if (drawCanvasRef.value) {
    const ctx = drawCanvasRef.value.getContext('2d')
    ctx.clearRect(0, 0, drawCanvasRef.value.width, drawCanvasRef.value.height)
  }
}

function loop() {
  if (!running.value) return
  // 移除 100ms 固定节流:推理完成后立即抓下一帧,由推理耗时自然限速
  frameTimer = setTimeout(captureAndInfer, 0)
}

async function captureAndInfer() {
  if (!running.value) return
  const video = videoRef.value
  const captureCanvas = canvasRef.value
  if (!video || !captureCanvas || video.readyState < 2) {
    loop()
    return
  }

  const t0 = performance.now()

  // 对齐 YOLO imgsz(480) 降采样，降低传输带宽 ~88%
  const vw = video.videoWidth || 640
  const vh = video.videoHeight || 480
  const CAPTURE_MAX = 480
  const scale = Math.min(1, CAPTURE_MAX / vw)
  const w = Math.round(vw * scale)
  const h = Math.round(vh * scale)
  captureCanvas.width = w
  captureCanvas.height = h
  const capCtx = captureCanvas.getContext('2d')
  capCtx.drawImage(video, 0, 0, vw, vh, 0, 0, w, h)
  const jpegQuality = mode.value === 'detect' ? 0.5 : 0.6
  const frame = captureCanvas.toDataURL('image/jpeg', jpegQuality)

  try {
    let result
    if (mode.value === 'detect') {
      // 性能优化:仅传检测框坐标,前端本地绘制(不再传 annotated 标注图)
      result = await detectFrame({ frame, conf: conf.value })
      detections.value = result.detections || []
      faces.value = []
      drawDetectionsLocally(detections.value, w, h)
    } else {
      if (!userId.value) {
        ui.pushToast({ type: 'warning', title: '用户信息缺失,无法识别人脸' })
        stopCamera()
        return
      }
      result = await recognizeFrame({ frame, user_id: userId.value })
      faces.value = result.faces || []
      detections.value = []
      drawFacesLocally(faces.value, w, h)
    }

    const dt = performance.now() - t0
    frameTimes.push(dt)
    if (frameTimes.length > 30) frameTimes.shift()
    const avg = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length
    fps.value = avg > 0 ? Math.round(1000 / avg) : 0
    // 推理成功:清空连续失败计数与历史错误提示
    if (failCount.value > 0) failCount.value = 0
    if (errorMsg.value) errorMsg.value = ''
  } catch (e) {
    const msg = e?.message || 'Yolo 推理失败'
    // 推理失败:不再强制关闭摄像头,只显示错误消息,让用户自行决定是否停止
    // 连续失败 N 次后提示用户检查 Yolo 服务,但仍不自动 stopCamera
    if (!e.response) {
      errorMsg.value = 'Yolo 推理失败: ' + msg + '。请在设置中检查 Yolo 服务状态。'
      failCount.value++
      if (failCount.value >= INFERENCE_FAIL_THRESHOLD) {
        ui.pushToast({
          type: 'warning',
          title: 'Yolo 服务异常',
          message: `连续 ${INFERENCE_FAIL_THRESHOLD} 次推理失败,请检查服务是否已启动`
        })
        failCount.value = 0
      }
    }
  } finally {
    loop()
  }
}

// 目标检测模式:在 video 当前帧上绘制 bbox + class + confidence(本地绘制)
// 坐标镜像:YOLO 收到的是原始未镜像帧,用户看到的是 CSS scaleX(-1) 镜像帧,
// 故需手动翻转 x 坐标(x_new = w - x_old)使框对齐用户所见画面。
// canvas 本身不做 CSS 镜像,文字保持正向可读。
function drawDetectionsLocally(detList, w, h) {
  const canvas = drawCanvasRef.value
  if (!canvas) return
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, w, h)
  detList.forEach((d) => {
    const [x1o, y1, x2o, y2] = d.bbox
    // x 坐标镜像
    const x1 = w - x2o
    const x2 = w - x1o
    const color = CLASS_COLORS[d.class_id % CLASS_COLORS.length]
    // 框
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
    // 标签
    const label = `${d.class} ${(d.confidence * 100).toFixed(0)}%`
    ctx.font = 'bold 14px JetBrains Mono, monospace'
    const tw = ctx.measureText(label).width + 10
    const th = 18
    // 溢出修复:标签右边界不超出画布,顶部不超出画布
    const labelX = Math.min(x1, w - tw)
    const labelY = Math.max(y1 - th, 0)
    ctx.fillStyle = color
    ctx.globalAlpha = 0.85
    ctx.fillRect(labelX, labelY, tw, th)
    ctx.globalAlpha = 1
    ctx.fillStyle = '#0b1020'
    ctx.fillText(label, labelX + 5, labelY + 14)
  })
}

function drawFacesLocally(faceList, w, h) {
  const canvas = drawCanvasRef.value
  if (!canvas) return
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, w, h)
  faceList.forEach((f) => {
    const [x1o, y1, x2o, y2] = f.bbox
    // x 坐标镜像(与检测模式同理)
    const x1 = w - x2o
    const x2 = w - x1o
    const known = !!f.name
    const color = known ? '#34d399' : '#f87171'
    ctx.strokeStyle = color
    ctx.lineWidth = 3
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
    const label = known ? `${f.name} ${(f.similarity * 100).toFixed(0)}%` : '未识别'
    ctx.font = 'bold 16px JetBrains Mono, monospace'
    const tw = ctx.measureText(label).width + 12
    const th = 22
    const labelX = Math.min(x1, w - tw)
    const labelY = Math.max(y1 - th, 0)
    ctx.fillStyle = known ? 'rgba(52, 211, 153, 0.9)' : 'rgba(248, 113, 113, 0.9)'
    ctx.fillRect(labelX, labelY, tw, th)
    ctx.fillStyle = '#0b1020'
    ctx.fillText(label, labelX + 6, labelY + 16)
  })
}

function switchMode(m) {
  if (mode.value === m) return
  mode.value = m
  detections.value = []
  faces.value = []
}

async function openFaceDialog() {
  await loadFaceLibrary()
  faceDialogVisible.value = true
}

async function refreshFaces() {
  await loadFaceLibrary()
  ui.pushToast({ type: 'success', title: '人脸库已刷新' })
}

async function captureRegister() {
  if (!registerName.value.trim()) {
    ui.pushToast({ type: 'warning', title: '请输入姓名' })
    return
  }
  if (!running.value) {
    ui.pushToast({ type: 'warning', title: '请先开启摄像头再采集注册' })
    return
  }
  capturing.value = true
  registerLoading.value = true
  try {
    const video = videoRef.value
    const captureCanvas = canvasRef.value
    const w = video.videoWidth || 640
    const h = video.videoHeight || 480
    captureCanvas.width = w
    captureCanvas.height = h
    captureCanvas.getContext('2d').drawImage(video, 0, 0, w, h)
    const frame = captureCanvas.toDataURL('image/jpeg', 0.8)

    const res = await addFace({ frame, name: registerName.value.trim() })
    faceLibrary.value.unshift(res)
    ui.pushToast({ type: 'success', title: `人脸 "${res.name}" 注册成功` })
    registerName.value = ''
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    capturing.value = false
    registerLoading.value = false
  }
}

async function deleteFace(face) {
  if (!window.confirm(`确定删除人脸 "${face.name}" 吗?`)) return
  try {
    await removeFace(face.id)
    faceLibrary.value = faceLibrary.value.filter((f) => f.id !== face.id)
    ui.pushToast({ type: 'success', title: '已删除' })
  } catch {
    /* 拦截器已提示 */
  }
}

function fmtTime(s) {
  if (!s) return ''
  return s.replace('T', ' ')
}

// ============ Yolo 设置面板 ============
async function openSettings() {
  settingsVisible.value = true
  await refreshSettings()
  // 打开设置时查询一次服务状态并启动轮询
  await refreshYoloServiceStatus()
  startYoloServicePolling()
}

async function closeSettings() {
  settingsVisible.value = false
  stopYoloServicePolling()
}

// 监听设置弹窗可见性:关闭时停止轮询(v-model 由 GlassModal 内部 X/遮罩关闭时触发)
watch(settingsVisible, (visible) => {
  if (!visible) {
    stopYoloServicePolling()
  }
})

async function refreshSettings() {
  if (!isDesktop.value) return
  settingsLoading.value = true
  try {
    // getYoloSettings() 内部已包含 models 列表，无需单独调 listModels()
    const settings = await getYoloSettings()
    if (settings) {
      yoloSettings.value = settings
      // 同步到 yoloUrl 显示
      yoloUrl.value = settings.yolo_service_url || 'http://127.0.0.1:6001'
      setYoloUrl(yoloUrl.value)
      // 同步模型存储目录(空字符串表示使用默认值)
      modelsDir.value = settings.models_dir || ''
      // 同步数据存储根目录
      dataDir.value = settings.data_dir || ''
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '读取设置失败', message: String(e?.message || e) })
  } finally {
    settingsLoading.value = false
  }
}

async function saveSettings() {
  if (!isDesktop.value) return
  settingsSaving.value = true
  try {
    const res = await saveYoloSettings({
      yolo_service_url: yoloSettings.value.yolo_service_url,
      yolo_device: yoloSettings.value.yolo_device,
      yolo_enabled: yoloSettings.value.yolo_enabled,
      yolo_imgsz: yoloSettings.value.yolo_imgsz
    })
    if (res && (res.success || res.ok)) {
      ui.pushToast({ type: 'success', title: 'Yolo 设置已保存' })
      // 更新运行时 yoloUrl
      yoloUrl.value = yoloSettings.value.yolo_service_url || 'http://127.0.0.1:6001'
      setYoloUrl(yoloUrl.value)
    } else {
      ui.pushToast({ type: 'danger', title: '保存失败', message: res?.message || '未知错误' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '保存失败', message: String(e?.message || e) })
  } finally {
    settingsSaving.value = false
  }
}

async function handleDownloadModel(modelName) {
  if (!isDesktop.value || downloadingModel.value) return
  downloadingModel.value = modelName
  // 清空旧的进度记录,避免显示上一次的进度条
  downloadingProgress.value = {
    ...downloadingProgress.value,
    [modelName]: { downloaded: 0, total: -1, percent: -1 }
  }
  ui.pushToast({ type: 'info', title: '开始下载', message: MODEL_LABELS[modelName] || modelName })
  try {
    const res = await downloadModel(modelName)
    if (res && res.ok) {
      // Python 侧已在线程中启动下载,实际结果通过 __modelDownloadProgress 回调推送
      // 此处不清理 downloadingModel,由回调在完成(percent>=100)或失败(percent=-2)时清理
    } else {
      // 启动失败(如目录不可用):立即清理下载中状态
      ui.pushToast({ type: 'danger', title: '下载失败', message: res?.error || res?.message || '未知错误' })
      downloadingModel.value = ''
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '下载失败', message: String(e?.message || e) })
    downloadingModel.value = ''
  }
}

async function handleInstallGpu() {
  if (!isDesktop.value || pipRunning.value) return
  pipRunning.value = true
  pipRunningPackage.value = 'gpu'
  pipLog.value = ''
  ui.pushToast({ type: 'info', title: '开始安装 GPU 库 (torch+CUDA)' })
  try {
    const res = await installGpuLib()
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: 'GPU 库安装成功' })
      await refreshSettings()
    } else {
      ui.pushToast({ type: 'danger', title: 'GPU 库安装失败', message: res?.error || '请查看日志' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '安装异常', message: String(e?.message || e) })
  } finally {
    pipRunning.value = false
    pipRunningPackage.value = ''
  }
}

async function handleInstallInsightface() {
  if (!isDesktop.value || pipRunning.value) return
  pipRunning.value = true
  pipRunningPackage.value = 'insightface'
  pipLog.value = ''
  ui.pushToast({ type: 'info', title: '开始安装 insightface 库' })
  try {
    const res = await installInsightfaceLib()
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: 'insightface 库安装成功' })
      await refreshSettings()
    } else {
      ui.pushToast({ type: 'danger', title: 'insightface 库安装失败', message: res?.error || '请查看日志' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '安装异常', message: String(e?.message || e) })
  } finally {
    pipRunning.value = false
    pipRunningPackage.value = ''
  }
}

// 一键安装全部依赖(GPU 模式)
async function handleInstallAllGpu() {
  if (!isDesktop.value || pipRunning.value) return
  pipRunning.value = true
  pipRunningPackage.value = 'all-gpu'
  pipLog.value = ''
  ui.pushToast({ type: 'info', title: '开始一键安装全部 GPU 依赖' })
  try {
    const res = await installAllDependencies('gpu')
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: '全部 GPU 依赖安装成功' })
      await refreshSettings()
    } else {
      ui.pushToast({ type: 'danger', title: '依赖安装失败', message: res?.error || '请查看日志' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '安装异常', message: String(e?.message || e) })
  } finally {
    pipRunning.value = false
    pipRunningPackage.value = ''
  }
}

// 一键安装全部依赖(CPU 模式)
async function handleInstallAllCpu() {
  if (!isDesktop.value || pipRunning.value) return
  pipRunning.value = true
  pipRunningPackage.value = 'all-cpu'
  pipLog.value = ''
  ui.pushToast({ type: 'info', title: '开始一键安装全部 CPU 依赖' })
  try {
    const res = await installAllDependencies('cpu')
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: '全部 CPU 依赖安装成功' })
      await refreshSettings()
    } else {
      ui.pushToast({ type: 'danger', title: '依赖安装失败', message: res?.error || '请查看日志' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '安装异常', message: String(e?.message || e) })
  } finally {
    pipRunning.value = false
    pipRunningPackage.value = ''
  }
}

// ============ 模型存储目录选择 ============
async function handleSelectModelsDir() {
  if (!isDesktop.value) return
  try {
    const res = await selectModelsDir()
    if (res && res.ok && res.path) {
      modelsDir.value = res.path
      ui.pushToast({ type: 'success', title: '模型目录已设置', message: res.path })
      // 刷新模型列表(目录变更后安装状态会变化)
      await refreshSettings()
    } else if (res && res.message) {
      ui.pushToast({ type: 'danger', title: '选择失败', message: res.message })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '选择目录异常', message: String(e?.message || e) })
  }
}

// ============ 数据存储路径选择 ============
async function handleSelectDataDir() {
  if (!isDesktop.value) return
  if (selectingDataDir.value) return
  selectingDataDir.value = true
  try {
    const res = await selectDataDir()
    if (res && res.ok && res.path) {
      dataDir.value = res.path
      ui.pushToast({ type: 'success', title: '数据存储路径已设置', message: res.path })
      // 刷新设置(目录变更后模型状态、依赖状态可能变化)
      await refreshSettings()
    } else if (res && res.message) {
      ui.pushToast({ type: 'danger', title: '选择失败', message: res.message })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '选择目录异常', message: String(e?.message || e) })
  } finally {
    selectingDataDir.value = false
  }
}

// ============ 运行硬件(CPU/GPU) + 服务 URL 保存 ============
async function saveDevice() {
  if (!isDesktop.value) return
  settingsSaving.value = true
  try {
    const res = await saveYoloSettings({
      yolo_device: yoloSettings.value.yolo_device || '',
      yolo_service_url: yoloSettings.value.yolo_service_url || ''
    })
    if (res && (res.success || res.ok)) {
      ui.pushToast({ type: 'success', title: '设置已保存' })
      // 同步运行时 yoloUrl
      yoloUrl.value = yoloSettings.value.yolo_service_url || 'http://127.0.0.1:6001'
      setYoloUrl(yoloUrl.value)
    } else {
      ui.pushToast({ type: 'danger', title: '保存失败', message: res?.message || '未知错误' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '保存失败', message: String(e?.message || e) })
  } finally {
    settingsSaving.value = false
  }
}

// ============ Yolo 服务启停 ============
async function handleStartYoloService() {
  if (!isDesktop.value || yoloServiceStarting.value) return
  yoloServiceStarting.value = true
  yoloServiceLog.value = ''
  ui.pushToast({ type: 'info', title: '正在启动 Yolo 服务…' })
  try {
    const res = await startYoloService()
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: 'Yolo 服务已启动', message: `PID: ${res.pid}` })
      await refreshYoloServiceStatus()
      // 等待 3 秒让服务完成预热,然后健康检查
      setTimeout(async () => {
        try {
          await yoloHealth()
          yoloReady.value = true
          ui.pushToast({ type: 'success', title: 'Yolo 服务就绪' })
        } catch {
          yoloReady.value = false
          ui.pushToast({ type: 'warning', title: 'Yolo 服务尚未就绪', message: '请查看服务日志' })
        }
      }, 3000)
    } else {
      ui.pushToast({ type: 'danger', title: '启动失败', message: res?.message || '未知错误' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '启动异常', message: String(e?.message || e) })
  } finally {
    yoloServiceStarting.value = false
  }
}

async function handleStopYoloService() {
  if (!isDesktop.value || yoloServiceStopping.value) return
  yoloServiceStopping.value = true
  ui.pushToast({ type: 'info', title: '正在停止 Yolo 服务…' })
  try {
    const res = await stopYoloService()
    if (res && res.ok) {
      ui.pushToast({ type: 'success', title: 'Yolo 服务已停止' })
    } else {
      ui.pushToast({ type: 'danger', title: '停止失败', message: res?.message || '未知错误' })
    }
  } catch (e) {
    ui.pushToast({ type: 'danger', title: '停止异常', message: String(e?.message || e) })
  } finally {
    yoloServiceStopping.value = false
    await refreshYoloServiceStatus()
  }
}

async function refreshYoloServiceStatus() {
  if (!isDesktop.value) return
  try {
    const st = await getYoloServiceStatus()
    if (st) {
      yoloServiceRunning.value = !!st.running
      yoloServicePid.value = st.pid || null
    }
  } catch {
    /* 静默 */
  }
}

function startYoloServicePolling() {
  stopYoloServicePolling()
  yoloServicePollTimer = setInterval(refreshYoloServiceStatus, 3000)
}

function stopYoloServicePolling() {
  if (yoloServicePollTimer) {
    clearInterval(yoloServicePollTimer)
    yoloServicePollTimer = null
  }
}

// 格式化下载字节数为可读字符串
function fmtBytes(n) {
  if (!n && n !== 0) return ''
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB'
  return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB'
}
</script>

<template>
  <div class="vision-page">
    <PageHeader title="视觉检测" subtitle="Yolo 目标检测 · 人脸识别" />

    <!-- 顶部状态条 -->
    <div class="status-bar">
      <div class="status-left">
        <span class="badge" :class="{ on: yoloReady, off: !yoloReady }">
          <span class="dot"></span>
          {{ yoloReady ? 'Yolo 在线' : 'Yolo 离线' }}
        </span>
        <span class="badge ghost" v-if="yoloUrl">{{ yoloUrl }}</span>
      </div>
      <div class="status-right">
        <button type="button" class="glass-btn status-btn" data-cursor-target @click="initEndpoint">
          <Icon name="refresh" :size="14" />
          重连
        </button>
        <button type="button" class="glass-btn status-btn" data-cursor-target @click="openSettings">
          <Icon name="settings" :size="14" />
          设置
        </button>
        <button type="button" class="glass-btn status-btn" data-cursor-target @click="openFaceDialog">
          <Icon name="user" :size="14" />
          人脸库
        </button>
      </div>
    </div>

    <!-- 主体:左控制 + 右显示 -->
    <div class="vision-grid">
      <!-- 左栏:控制面板 -->
      <section class="glass-card ctrl-panel">
        <div class="panel-head">
          <span class="panel-tag">Control</span>
          <h3 class="panel-title">视觉检测控制台</h3>
        </div>

        <!-- 模式切换 -->
        <div class="mode-switch">
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'detect' }"
            data-cursor-target
            @click="switchMode('detect')"
          >
            <Icon name="eye" :size="16" />
            <span>目标检测</span>
          </button>
          <button
            type="button"
            class="mode-btn"
            :class="{ active: mode === 'recognize' }"
            data-cursor-target
            @click="switchMode('recognize')"
          >
            <Icon name="user" :size="16" />
            <span>人脸识别</span>
          </button>
        </div>

        <!-- 摄像头控制 -->
        <div class="ctrl-row">
          <button
            v-if="!running"
            type="button"
            class="glass-btn glass-btn--primary cam-btn"
            :disabled="!yoloReady"
            data-cursor-target
            @click="startCamera"
          >
            <Icon name="play" :size="16" />
            开启摄像头
          </button>
          <button
            v-else
            type="button"
            class="glass-btn cam-btn cam-btn--stop"
            data-cursor-target
            @click="stopCamera"
          >
            <Icon name="pause" :size="16" />
            停止
          </button>
        </div>

        <!-- 检测参数(仅目标检测模式) -->
        <div class="ctrl-block" v-if="mode === 'detect'">
          <div class="ctrl-label">
            <span>置信度阈值</span>
            <span class="val">{{ conf.toFixed(2) }}</span>
          </div>
          <input
            v-model.number="conf"
            type="range"
            min="0.1"
            max="0.9"
            step="0.05"
            class="conf-slider"
          />
        </div>

        <!-- 人脸识别提示 -->
        <div class="ctrl-block" v-if="mode === 'recognize'">
          <div class="hint-card glass-light">
            <p>当前已注册人脸:<b>{{ faceLibrary.length }}</b> 人</p>
            <p class="muted" v-if="!hasFaces">暂无人脸,请先到"人脸库"注册</p>
            <p class="muted" v-else>识别由 Yolo 本地比对,注册后约 30 秒生效</p>
          </div>
        </div>

        <!-- 性能指标 -->
        <div class="metrics">
          <div class="metric glass-light">
            <div class="metric-label">FPS</div>
            <div class="metric-val">{{ fps }}</div>
          </div>
          <div class="metric glass-light">
            <div class="metric-label">{{ mode === 'detect' ? '检测目标' : '识别人脸' }}</div>
            <div class="metric-val">{{ mode === 'detect' ? detections.length : faces.length }}</div>
          </div>
        </div>

        <!-- 离线/错误提示 -->
        <div class="err-card" v-if="errorMsg">
          <Icon name="warning" :size="14" />
          <span>{{ errorMsg }}</span>
        </div>
      </section>

      <!-- 右栏:显示区 -->
      <section class="glass-card display-panel">
        <div class="panel-head">
          <span class="panel-tag">Live</span>
          <h3 class="panel-title">
            {{ mode === 'detect' ? '目标检测画面' : '人脸识别画面' }}
          </h3>
        </div>

        <div class="video-wrap">
          <video ref="videoRef" autoplay playsinline muted></video>
          <canvas ref="drawCanvasRef" class="overlay"></canvas>
          <canvas ref="canvasRef" class="hidden-canvas"></canvas>

          <div class="placeholder" v-if="!running">
            <Icon name="eye" :size="48" />
            <p>{{ yoloReady ? '点击"开启摄像头"开始' : 'Yolo 服务离线' }}</p>
          </div>
        </div>

        <!-- 结果列表 -->
        <div class="result-wrap">
          <div class="result-head">
            {{ mode === 'detect' ? '检测结果' : '识别结果' }}
          </div>
          <ul class="result-list" v-if="mode === 'detect'">
            <li v-for="(d, i) in detections" :key="'d' + i" class="result-item">
              <span class="r-class">{{ d.class }}</span>
              <span class="r-conf">{{ (d.confidence * 100).toFixed(1) }}%</span>
              <span class="r-bbox">[{{ d.bbox.join(', ') }}]</span>
            </li>
            <li v-if="detections.length === 0" class="empty">暂无检测目标</li>
          </ul>
          <ul class="result-list" v-else>
            <li v-for="(f, i) in faces" :key="'f' + i" class="result-item face">
              <span class="r-class" :class="{ known: f.name, unknown: !f.name }">
                {{ f.name || '未识别' }}
              </span>
              <span class="r-sim" v-if="f.name">{{ (f.similarity * 100).toFixed(1) }}%</span>
              <span class="r-bbox">[{{ f.bbox.join(', ') }}]</span>
            </li>
            <li v-if="faces.length === 0" class="empty">暂无识别人脸</li>
          </ul>
        </div>
      </section>
    </div>

    <!-- 人脸库管理弹窗 -->
    <GlassModal v-model="faceDialogVisible" title="人脸库管理" size="lg">
      <div class="reg-row">
        <input
          v-model="registerName"
          class="glass-input reg-input"
          placeholder="输入姓名"
          maxlength="64"
          @keyup.enter="captureRegister"
        />
        <button
          type="button"
          class="glass-btn glass-btn--primary"
          :disabled="!running || !registerName.trim() || registerLoading"
          data-cursor-target
          @click="captureRegister"
        >
          <Icon v-if="registerLoading" name="refresh" :size="14" class="spin" />
          <Icon v-else name="plus" :size="14" />
          采集注册
        </button>
        <button type="button" class="glass-btn" data-cursor-target @click="refreshFaces">
          <Icon name="refresh" :size="14" />
        </button>
      </div>
      <p class="reg-hint" v-if="!running">
        <Icon name="play" :size="14" />
        请先在主界面开启摄像头,再采集注册
      </p>

      <div class="face-table-wrap">
        <table class="face-table">
          <thead>
            <tr>
              <th style="width:72px">样张</th>
              <th>姓名</th>
              <th style="width:180px">注册时间</th>
              <th style="width:80px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="face in faceLibrary" :key="face.id">
              <td>
                <img v-if="face.sample_snapshot" :src="face.sample_snapshot" class="thumb" alt="snapshot" />
                <span v-else class="no-snap">—</span>
              </td>
              <td>{{ face.name }}</td>
              <td>{{ fmtTime(face.created_at) }}</td>
              <td>
                <button type="button" class="del-btn" data-cursor-target @click="deleteFace(face)">
                  <Icon name="trash" :size="14" />
                </button>
              </td>
            </tr>
            <tr v-if="faceLibrary.length === 0">
              <td colspan="4" class="empty-row">暂无人脸</td>
            </tr>
          </tbody>
        </table>
      </div>
    </GlassModal>

    <!-- Yolo 设置弹窗 -->
    <GlassModal v-model="settingsVisible" title="Yolo 视觉服务设置" size="xl">
      <div v-if="settingsLoading" class="settings-loading">
        <Icon name="refresh" :size="18" class="spin" />
        <span>加载设置中…</span>
      </div>

      <div v-else class="settings-body">
        <!-- 区域0:数据存储路径 -->
        <div class="settings-section">
          <div class="settings-section-head">
            <span class="settings-dot" />
            <span class="settings-label">数据存储路径</span>
          </div>
          <div class="settings-field">
            <label class="settings-field-label">存储根目录</label>
            <div class="dir-row">
              <input
                :value="dataDir || '(使用默认目录)'"
                class="glass-input settings-input"
                readonly
                placeholder="(使用默认目录)"
                data-cursor-target
              />
              <button
                type="button"
                class="glass-btn glass-btn--primary dir-btn"
                :disabled="selectingDataDir"
                data-cursor-target
                @click="handleSelectDataDir"
              >
                <Icon v-if="selectingDataDir" name="refresh" :size="14" class="spin" />
                <Icon v-else name="folder" :size="14" />
                选择文件夹
              </button>
            </div>
            <p class="settings-hint">
              Python 运行时、模型文件和配置文件统一存放在此目录。模型存储在：{{ dataDir ? dataDir + '/models/' : '(默认目录)/models/' }}
            </p>
          </div>
        </div>

        <!-- 区域2:运行硬件 -->
        <div class="settings-section">
          <div class="settings-section-head">
            <span class="settings-dot" :class="{ on: yoloSettings.gpu?.gpu_available }" />
            <span class="settings-label">运行硬件</span>
          </div>
          <div class="dep-grid">
            <div class="dep-item">
              <span class="dep-name">CUDA 可用</span>
              <span class="dep-state" :class="yoloSettings.gpu?.gpu_available ? 'ok' : 'no'">
                {{ yoloSettings.gpu?.gpu_available ? '是' : '否' }}
              </span>
            </div>
            <div class="dep-item" v-if="yoloSettings.gpu?.device_count > 0">
              <span class="dep-name">GPU 数量</span>
              <span class="dep-state ok">{{ yoloSettings.gpu.device_count }}</span>
            </div>
            <div class="dep-item" v-if="yoloSettings.gpu?.devices?.length">
              <span class="dep-name">设备</span>
              <span class="dep-state ok">{{ yoloSettings.gpu.devices.join(', ') }}</span>
            </div>
            <div class="dep-item" v-if="yoloSettings.gpu?.error">
              <span class="dep-name">错误</span>
              <span class="dep-state no">{{ yoloSettings.gpu.error }}</span>
            </div>
          </div>
          <div class="settings-field">
            <label class="settings-field-label">推理设备</label>
            <select
              v-model="yoloSettings.yolo_device"
              class="glass-input settings-input"
              data-cursor-target
            >
              <option value="">自动 (有 GPU 用 GPU,否则 CPU)</option>
              <option value="cpu">强制 CPU</option>
              <option value="0">强制 GPU 0</option>
            </select>
            <p class="settings-hint">
              空=自动检测; "cpu"=强制 CPU; "0"=强制 GPU0。修改后点击"保存硬件设置"。
            </p>
          </div>
          <div class="settings-actions">
            <button
              type="button"
              class="glass-btn glass-btn--primary"
              :disabled="settingsSaving"
              data-cursor-target
              @click="saveDevice"
            >
              <Icon v-if="settingsSaving" name="refresh" :size="14" class="spin" />
              <Icon v-else name="check" :size="14" />
              保存硬件设置
            </button>
            <button type="button" class="glass-btn" data-cursor-target @click="refreshSettings">
              <Icon name="refresh" :size="14" />
              刷新状态
            </button>
          </div>
          <!-- Yolo 服务 URL(供 Web 模式直连,桌面端推理走桥接) -->
          <div class="settings-field">
            <label class="settings-field-label">Yolo 服务 URL (Web 模式直连用)</label>
            <input
              v-model="yoloSettings.yolo_service_url"
              class="glass-input settings-input"
              placeholder="http://127.0.0.1:6001"
              data-cursor-target
            />
            <p class="settings-hint">
              默认 http://127.0.0.1:6001。桌面端推理走本地 Python 桥接,此地址供 Web 模式直连使用。
            </p>
          </div>
        </div>

        <!-- 区域3:Python 依赖 -->
        <div class="settings-section">
          <div class="settings-section-head">
            <span class="settings-dot" />
            <span class="settings-label">Python 依赖</span>
          </div>
          <div class="dep-grid">
            <div class="dep-item" v-for="(installed, pkg) in yoloSettings.dependencies" :key="pkg">
              <span class="dep-name">{{ pkg }}</span>
              <span class="dep-state" :class="installed ? 'ok' : 'no'">
                {{ installed ? '已安装' : '未安装' }}
              </span>
            </div>
          </div>
          <div class="dep-actions">
            <button
              type="button"
              class="glass-btn glass-btn--primary dep-btn"
              :disabled="pipRunning"
              data-cursor-target
              @click="handleInstallAllGpu"
            >
              <Icon v-if="pipRunningPackage === 'all-gpu'" name="refresh" :size="14" class="spin" />
              <Icon v-else name="download" :size="14" />
              一键安装全部 (GPU)
            </button>
            <button
              type="button"
              class="glass-btn glass-btn--primary dep-btn"
              :disabled="pipRunning"
              data-cursor-target
              @click="handleInstallAllCpu"
            >
              <Icon v-if="pipRunningPackage === 'all-cpu'" name="refresh" :size="14" class="spin" />
              <Icon v-else name="download" :size="14" />
              一键安装全部 (CPU)
            </button>
            <button
              type="button"
              class="glass-btn dep-btn"
              :disabled="pipRunning"
              data-cursor-target
              @click="handleInstallGpu"
            >
              <Icon v-if="pipRunningPackage === 'gpu'" name="refresh" :size="14" class="spin" />
              <Icon v-else name="download" :size="14" />
              安装 GPU 库 (torch+CUDA)
            </button>
            <button
              type="button"
              class="glass-btn dep-btn"
              :disabled="pipRunning"
              data-cursor-target
              @click="handleInstallInsightface"
            >
              <Icon v-if="pipRunningPackage === 'insightface'" name="refresh" :size="14" class="spin" />
              <Icon v-else name="download" :size="14" />
              安装 insightface 库
            </button>
          </div>
          <p class="settings-hint">
            GPU 模式: torch+torchvision+torchaudio (CUDA 12.1) + ultralytics + insightface + onnxruntime-gpu + opencv-python-headless + numpy<br/>
            CPU 模式: torch+torchvision+torchaudio + ultralytics + insightface + onnxruntime + opencv-python-headless + numpy
          </p>
          <div v-if="pipLog" class="pip-log-wrap">
            <div class="pip-log-head">
              <span>安装日志</span>
              <button type="button" class="pip-clear" data-cursor-target @click="pipLog = ''">清空</button>
            </div>
            <pre class="pip-log">{{ pipLog }}</pre>
          </div>
        </div>

        <!-- 区域4:模型下载 -->
        <div class="settings-section">
          <div class="settings-section-head">
            <span class="settings-dot" />
            <span class="settings-label">模型下载</span>
          </div>
          <div class="model-list">
            <div
              v-for="model in yoloSettings.models"
              :key="model.name"
              class="model-item"
            >
              <div class="model-info">
                <span class="model-name">{{ MODEL_LABELS[model.name] || model.name }}</span>
                <span class="model-state" :class="model.installed ? 'ok' : 'no'">
                  {{ model.installed ? `已安装${model.size_mb ? ' (' + model.size_mb + ' MB)' : ''}` : '未安装' }}
                </span>
                <!-- 下载进度条 -->
                <div
                  v-if="downloadingModel === model.name && downloadingProgress[model.name]"
                  class="model-progress"
                >
                  <div class="progress-bar">
                    <div
                      class="progress-fill"
                      :style="{ width: Math.max(0, Math.min(100, downloadingProgress[model.name].percent)).toFixed(1) + '%' }"
                    />
                  </div>
                  <span class="progress-text">
                    {{ downloadingProgress[model.name].percent.toFixed(1) }}%
                    <span v-if="downloadingProgress[model.name].total > 0">
                      ({{ fmtBytes(downloadingProgress[model.name].downloaded) }} / {{ fmtBytes(downloadingProgress[model.name].total) }})
                    </span>
                  </span>
                </div>
              </div>
              <button
                v-if="!model.installed"
                type="button"
                class="glass-btn glass-btn--primary model-btn"
                :disabled="downloadingModel === model.name"
                data-cursor-target
                @click="handleDownloadModel(model.name)"
              >
                <Icon v-if="downloadingModel === model.name" name="refresh" :size="14" class="spin" />
                <Icon v-else name="download" :size="14" />
                {{ downloadingModel === model.name ? '下载中…' : '下载' }}
              </button>
              <span v-else class="model-ready">
                <Icon name="check" :size="14" />
                就绪
              </span>
            </div>
            <p v-if="!yoloSettings.models.length" class="model-empty">
              暂无模型信息,请点击"刷新状态"
            </p>
          </div>
        </div>

        <!-- 区域5:Yolo 服务启停 -->
        <div class="settings-section">
          <div class="settings-section-head">
            <span class="settings-dot" :class="{ on: yoloServiceRunning }" />
            <span class="settings-label">Yolo 服务启停</span>
          </div>
          <div class="service-status-row">
            <div class="dep-item service-status-item">
              <span class="dep-name">服务状态</span>
              <span class="dep-state" :class="yoloServiceRunning ? 'ok' : 'no'">
                {{ yoloServiceRunning ? '运行中' : '已停止' }}
              </span>
            </div>
            <div class="dep-item" v-if="yoloServicePid">
              <span class="dep-name">PID</span>
              <span class="dep-state ok">{{ yoloServicePid }}</span>
            </div>
            <div class="dep-item">
              <span class="dep-name">端口</span>
              <span class="dep-state ok">6001</span>
            </div>
          </div>
          <div class="dep-actions">
            <button
              type="button"
              class="glass-btn glass-btn--primary dep-btn"
              :disabled="yoloServiceStarting || yoloServiceRunning"
              data-cursor-target
              @click="handleStartYoloService"
            >
              <Icon v-if="yoloServiceStarting" name="refresh" :size="14" class="spin" />
              <Icon v-else name="play" :size="14" />
              启动 Yolo 服务
            </button>
            <button
              type="button"
              class="glass-btn dep-btn service-stop-btn"
              :disabled="yoloServiceStopping || !yoloServiceRunning"
              data-cursor-target
              @click="handleStopYoloService"
            >
              <Icon v-if="yoloServiceStopping" name="refresh" :size="14" class="spin" />
              <Icon v-else name="pause" :size="14" />
              停止 Yolo 服务
            </button>
          </div>
          <div v-if="yoloServiceLog" class="pip-log-wrap">
            <div class="pip-log-head">
              <span>服务日志</span>
              <button type="button" class="pip-clear" data-cursor-target @click="yoloServiceLog = ''">清空</button>
            </div>
            <pre class="pip-log">{{ yoloServiceLog }}</pre>
          </div>
          <p class="settings-hint">
            启动 Yolo Flask 服务(监听 6001 端口)。首次启动需加载模型,可能耗时较长。状态每 3 秒自动刷新。
          </p>
        </div>
      </div>
    </GlassModal>
  </div>
</template>

<style scoped>
.vision-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* ===== 状态条 ===== */
.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.status-left, .status-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid var(--glass-border);
  background: var(--glass-light);
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}
.badge .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-tertiary);
}
.badge.on {
  color: var(--mint);
  border-color: rgba(52, 211, 153, 0.3);
  background: rgba(52, 211, 153, 0.08);
}
.badge.on .dot {
  background: var(--mint);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.6);
}
.badge.off {
  color: var(--color-danger);
  border-color: rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.08);
}
.badge.off .dot {
  background: var(--color-danger);
}
.badge.ghost {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-tertiary);
}
.status-btn {
  padding: 0.5rem 1rem;
  font-size: 0.8rem;
}

/* ===== 主体双栏 ===== */
.vision-grid {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 18px;
  align-items: start;
}
@media (max-width: 1100px) {
  .vision-grid {
    grid-template-columns: 1fr;
  }
}

/* ===== 面板基础 ===== */
.ctrl-panel, .display-panel {
  padding: 20px 22px;
}
.panel-head {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--glass-border);
}
.panel-tag {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.panel-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
}

/* ===== 控制面板 ===== */
.mode-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 18px;
}
.mode-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 8px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--glass-light);
  color: var(--text-tertiary);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.2s ease;
}
.mode-btn:hover {
  border-color: rgba(132, 204, 22, 0.22);
  color: var(--text-secondary);
}
.mode-btn.active {
  border-color: rgba(52, 211, 153, 0.3);
  color: var(--mint);
  background: rgba(52, 211, 153, 0.08);
}
.ctrl-row {
  margin-bottom: 18px;
}
.cam-btn {
  width: 100%;
  justify-content: center;
}
.cam-btn--stop {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.3);
  color: var(--color-danger);
}
.ctrl-block {
  margin-bottom: 18px;
}
.ctrl-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.ctrl-label .val {
  color: var(--mint);
  font-family: 'JetBrains Mono', monospace;
}
.conf-slider {
  width: 100%;
  height: 4px;
  border-radius: 999px;
  background: var(--glass-medium);
  outline: none;
  -webkit-appearance: none;
  appearance: none;
}
.conf-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--mint);
  cursor: pointer;
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.4);
}
.conf-slider::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--mint);
  cursor: pointer;
  border: none;
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.4);
}
.hint-card {
  padding: 12px 14px;
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-secondary);
}
.hint-card p {
  margin: 0 0 6px;
}
.hint-card p:last-child {
  margin-bottom: 0;
}
.hint-card b {
  color: var(--mint);
}
.muted {
  color: var(--text-tertiary);
  font-size: 12px;
}

/* ===== 性能指标 ===== */
.metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--glass-border);
}
.metric {
  text-align: center;
  padding: 10px 8px;
  border-radius: var(--radius-md);
}
.metric-label {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}
.metric-val {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}

/* ===== 错误卡片 ===== */
.err-card {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  border: 1px solid rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.08);
  color: var(--color-danger);
  font-size: 12px;
}

/* ===== 显示面板 ===== */
.video-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--bg-deep);
  border-radius: var(--radius-md);
  overflow: hidden;
  border: 1px solid var(--glass-border);
}
.video-wrap video,
.video-wrap .overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.video-wrap .overlay {
  pointer-events: none;
  z-index: 2;
}
.video-wrap video {
  z-index: 1;
  transform: scaleX(-1);
}
.hidden-canvas {
  display: none;
}
.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-tertiary);
  z-index: 3;
  background: var(--bg-deep);
}
.placeholder p {
  margin: 0;
  font-size: 13px;
}

/* ===== 结果列表 ===== */
.result-wrap {
  margin-top: 16px;
}
.result-head {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  margin-bottom: 8px;
}
.result-list {
  list-style: none;
  padding: 0;
  margin: 0;
  /* 固定高度避免检测结果数量变化时卡片跳动 */
  height: 180px;
  overflow-y: auto;
}
.result-item {
  display: grid;
  grid-template-columns: 1.4fr 0.8fr 1.8fr;
  gap: 12px;
  padding: 8px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--glass-border);
  align-items: center;
}
.result-item:last-child {
  border-bottom: none;
}
.result-item:hover {
  background: rgba(52, 211, 153, 0.05);
}
.r-class {
  color: var(--text-primary);
  font-weight: 500;
}
.r-class.known {
  color: var(--mint);
}
.r-class.unknown {
  color: var(--color-danger);
}
.r-conf, .r-sim {
  color: var(--amber);
  font-size: 12px;
  font-family: 'JetBrains Mono', monospace;
}
.r-sim {
  color: var(--mint);
}
.r-bbox {
  color: var(--text-tertiary);
  font-size: 11px;
  font-family: 'JetBrains Mono', monospace;
}
.empty {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 12px;
  padding: 20px;
}

/* ===== 人脸库弹窗 ===== */
.reg-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.reg-input {
  flex: 1;
}
.reg-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--amber);
  font-size: 12px;
  margin: 0 0 14px;
}
.face-table-wrap {
  overflow-x: auto;
}
.face-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.face-table th {
  text-align: left;
  padding: 8px 10px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--glass-border);
}
.face-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--glass-border);
  color: var(--text-secondary);
}
.face-table tr:last-child td {
  border-bottom: none;
}
.face-table .thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}
.no-snap {
  color: var(--text-tertiary);
}
.del-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 1px solid rgba(248, 113, 113, 0.3);
  background: rgba(248, 113, 113, 0.08);
  color: var(--color-danger);
  cursor: pointer;
  transition: all 0.2s ease;
}
.del-btn:hover {
  background: rgba(248, 113, 113, 0.15);
}
.empty-row {
  text-align: center;
  color: var(--text-tertiary);
  padding: 20px;
}

.spin {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== Yolo 设置弹窗 ===== */
.settings-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 0;
  color: var(--text-tertiary);
  font-family: 'DM Sans', sans-serif;
  font-size: 13px;
}
.settings-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-height: 70vh;
  overflow-y: auto;
  padding-right: 6px;
}
.settings-body::-webkit-scrollbar {
  width: 6px;
}
.settings-body::-webkit-scrollbar-thumb {
  background: rgba(132, 204, 22, 0.18);
  border-radius: 3px;
}
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.settings-section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--glass-border);
}
.settings-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-tertiary);
}
.settings-dot.on {
  background: var(--mint);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.6);
}
.settings-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-secondary);
}
.settings-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.settings-field-label {
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
.settings-input {
  border-radius: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
}
.settings-hint {
  margin: 0;
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-tertiary);
}
.settings-actions {
  display: flex;
  gap: 10px;
}
.settings-actions .glass-btn {
  height: 38px;
  padding: 0 18px;
  border-radius: 10px;
  font-size: 13px;
}

/* 依赖网格 */
.dep-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.dep-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
  font-size: 12px;
}
.dep-name {
  color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
}
.dep-state {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
}
.dep-state.ok {
  color: var(--mint);
  background: rgba(52, 211, 153, 0.12);
}
.dep-state.no {
  color: var(--color-danger);
  background: rgba(248, 113, 113, 0.12);
}
.dep-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.dep-btn {
  height: 38px;
  padding: 0 16px;
  border-radius: 10px;
  font-size: 12px;
  white-space: nowrap;
}

/* pip 安装日志 */
.pip-log-wrap {
  margin-top: 8px;
  border-radius: var(--radius-md);
  background: var(--bg-deep, #0a0f14);
  border: 1px solid var(--glass-border);
  overflow: hidden;
}
.pip-log-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-family: 'DM Sans', sans-serif;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
  border-bottom: 1px solid var(--glass-border);
}
.pip-clear {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 6px;
  transition: background 0.2s ease, color 0.2s ease;
}
.pip-clear:hover {
  background: var(--glass-light);
  color: var(--text-primary);
}
.pip-log {
  margin: 0;
  padding: 12px;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

/* 模型列表 */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--glass-light);
  border: 1px solid var(--glass-border);
}
.model-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.model-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}
.model-state {
  font-size: 11px;
  font-weight: 600;
}
.model-state.ok {
  color: var(--mint);
}
.model-state.no {
  color: var(--color-danger);
}
.model-btn {
  height: 34px;
  padding: 0 16px;
  border-radius: 8px;
  font-size: 12px;
  white-space: nowrap;
  flex-shrink: 0;
}
.model-ready {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--mint);
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.model-empty {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 12px;
  padding: 16px;
}

/* ===== 模型目录选择行 ===== */
.dir-row {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.dir-row .settings-input {
  flex: 1;
  min-width: 0;
}
.dir-btn {
  height: auto;
  padding: 0 16px;
  border-radius: 10px;
  font-size: 12px;
  white-space: nowrap;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

/* ===== 模型下载进度条 ===== */
.model-progress {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
}
.progress-bar {
  width: 100%;
  height: 6px;
  border-radius: 999px;
  background: var(--glass-medium);
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--mint), #6ee7b7);
  border-radius: 999px;
  transition: width 0.2s ease;
}
.progress-text {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: 'JetBrains Mono', monospace;
}

/* ===== Yolo 服务状态行 ===== */
.service-status-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.service-status-item {
  flex: 1;
  min-width: 160px;
}
.service-stop-btn {
  background: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.3);
  color: var(--color-danger);
}
.service-stop-btn:not(:disabled):hover {
  background: rgba(248, 113, 113, 0.2);
}
</style>
