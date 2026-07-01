<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useUserStore } from '@/stores/user'
import { useUiStore } from '@/stores/ui'
import { getEndpoint, listFaces, addFace, removeFace } from '@/api/vision'
import { setYoloUrl, getYoloUrl, health as yoloHealth, detectFrame, recognizeFrame } from '@/api/yolo'
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

const videoRef = ref(null)
const canvasRef = ref(null)
const drawCanvasRef = ref(null)
let stream = null
let frameTimer = null
let frameTimes = []

const userId = computed(() => userStore.user?.id)
const hasFaces = computed(() => faceLibrary.value.length > 0)

onMounted(async () => {
  await initEndpoint()
  await loadFaceLibrary()
})

onUnmounted(() => {
  stopCamera()
})

async function initEndpoint() {
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

  const w = video.videoWidth || 640
  const h = video.videoHeight || 480
  captureCanvas.width = w
  captureCanvas.height = h
  const capCtx = captureCanvas.getContext('2d')
  capCtx.drawImage(video, 0, 0, w, h)
  const frame = captureCanvas.toDataURL('image/jpeg', 0.8)

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
  } catch (e) {
    if (!e.response) {
      yoloReady.value = false
      errorMsg.value = 'Yolo 服务连接失败,已停止推理'
      stopCamera()
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
        <button class="glass-btn status-btn" data-cursor-target @click="initEndpoint">
          <Icon name="refresh" :size="14" />
          重连
        </button>
        <button class="glass-btn status-btn" data-cursor-target @click="openFaceDialog">
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
            class="mode-btn"
            :class="{ active: mode === 'detect' }"
            data-cursor-target
            @click="switchMode('detect')"
          >
            <Icon name="eye" :size="16" />
            <span>目标检测</span>
          </button>
          <button
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
          class="glass-btn glass-btn--primary"
          :disabled="!running || !registerName.trim() || registerLoading"
          data-cursor-target
          @click="captureRegister"
        >
          <Icon v-if="registerLoading" name="refresh" :size="14" class="spin" />
          <Icon v-else name="plus" :size="14" />
          采集注册
        </button>
        <button class="glass-btn" data-cursor-target @click="refreshFaces">
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
                <button class="del-btn" data-cursor-target @click="deleteFace(face)">
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
</style>
