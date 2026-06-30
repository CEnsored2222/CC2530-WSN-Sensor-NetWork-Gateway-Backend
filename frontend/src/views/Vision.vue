<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Camera, VideoPause, VideoPlay, User, Delete, Plus, Refresh, Aim } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'
import { getEndpoint, listFaces, addFace, removeFace } from '@/api/vision'
import { setYoloUrl, getYoloUrl, health as yoloHealth, detectFrame, recognizeFrame } from '@/api/yolo'

const userStore = useUserStore()

// ============ 状态 ============
const mode = ref('detect')              // detect | recognize
const running = ref(false)              // 摄像头是否开启
const yoloReady = ref(false)            // Yolo 服务是否可达
const yoloUrl = ref('')                 // Yolo 服务地址(展示用)
const conf = ref(0.35)                  // 检测置信度阈值
const fps = ref(0)
const detections = ref([])              // 检测结果
const faces = ref([])                   // 识别结果
const errorMsg = ref('')                // 最近一次错误
const faceLibrary = ref([])             // 当前用户人脸库
const faceDialogVisible = ref(false)    // 人脸库管理弹窗
const registerName = ref('')
const registerLoading = ref(false)
const capturing = ref(false)

// ============ DOM 引用 ============
const videoRef = ref(null)
const canvasRef = ref(null)             // 用于抓帧(隐藏)
const drawCanvasRef = ref(null)         // 用于绘制标注(显示)
let stream = null
let frameTimer = null
let frameTimes = []                     // 最近 30 帧耗时(ms)

// ============ 计算属性 ============
const userId = computed(() => userStore.user?.id)
const hasFaces = computed(() => faceLibrary.value.length > 0)

// ============ 页面初始化 ============
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
      // 探测 Yolo /health
      try {
        await yoloHealth()
        yoloReady.value = true
      } catch {
        yoloReady.value = false
        ElMessage.warning('Yolo 视觉服务离线,请联系管理员')
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

// ============ 摄像头与逐帧推理 ============
async function startCamera() {
  if (!yoloReady.value) {
    ElMessage.warning('Yolo 视觉服务离线,无法启动推理')
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
    ElMessage.error(errorMsg.value)
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
  // 清空绘制画布
  if (drawCanvasRef.value) {
    const ctx = drawCanvasRef.value.getContext('2d')
    ctx.clearRect(0, 0, drawCanvasRef.value.width, drawCanvasRef.value.height)
  }
}

function loop() {
  if (!running.value) return
  frameTimer = setTimeout(captureAndInfer, 100)
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

  // 抓帧到隐藏 canvas → JPEG base64
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
      result = await detectFrame({ frame, conf: conf.value })
      detections.value = result.detections || []
      faces.value = []
      // 绘制 Yolo 返回的标注图
      drawAnnotated(result.annotated, w, h)
    } else {
      // 人脸识别模式:user_id 从 user store 解出
      if (!userId.value) {
        ElMessage.warning('用户信息缺失,无法识别人脸')
        stopCamera()
        return
      }
      result = await recognizeFrame({ frame, user_id: userId.value })
      faces.value = result.faces || []
      detections.value = []
      // 人脸识别无标注图,本地绘制 bbox + name
      drawFacesLocally(faces.value, w, h, video)
    }

    // FPS 统计
    const dt = performance.now() - t0
    frameTimes.push(dt)
    if (frameTimes.length > 30) frameTimes.shift()
    const avg = frameTimes.reduce((a, b) => a + b, 0) / frameTimes.length
    fps.value = avg > 0 ? Math.round(1000 / avg) : 0
  } catch (e) {
    // 直连失败:不弹消息(避免逐帧弹窗),仅标记离线
    if (!e.response) {
      yoloReady.value = false
      errorMsg.value = 'Yolo 服务连接失败,已停止推理'
      stopCamera()
    }
  } finally {
    loop()
  }
}

// 绘制 Yolo 返回的标注图(data:image/jpeg;base64,...)
function drawAnnotated(annotatedB64, w, h) {
  const canvas = drawCanvasRef.value
  if (!canvas) return
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!annotatedB64) {
    ctx.clearRect(0, 0, w, h)
    return
  }
  const img = new Image()
  img.onload = () => {
    ctx.drawImage(img, 0, 0, w, h)
  }
  img.src = annotatedB64
}

// 人脸识别模式:在 video 当前帧上绘制 bbox + name + similarity
function drawFacesLocally(faceList, w, h, video) {
  const canvas = drawCanvasRef.value
  if (!canvas) return
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  // 先绘制 video 当前帧
  ctx.drawImage(video, 0, 0, w, h)
  // 绘制每个人脸框
  faceList.forEach((f) => {
    const [x1, y1, x2, y2] = f.bbox
    const known = !!f.name
    ctx.strokeStyle = known ? '#4dd6c1' : '#ef6b7e'
    ctx.lineWidth = 3
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
    // 标签背景
    const label = known ? `${f.name} ${(f.similarity * 100).toFixed(0)}%` : '未识别'
    ctx.font = 'bold 16px IBM Plex Sans, sans-serif'
    const tw = ctx.measureText(label).width + 12
    ctx.fillStyle = known ? 'rgba(77, 214, 193, 0.9)' : 'rgba(239, 107, 126, 0.9)'
    ctx.fillRect(x1, Math.max(y1 - 24, 0), tw, 22)
    ctx.fillStyle = '#0b1020'
    ctx.fillText(label, x1 + 6, Math.max(y1 - 8, 14))
  })
}

// ============ 模式切换 ============
function switchMode(m) {
  if (mode.value === m) return
  mode.value = m
  detections.value = []
  faces.value = []
  if (running.value) {
    // 切换模式不重启摄像头,下一帧自动走新分支
  }
}

// ============ 人脸库管理 ============
async function openFaceDialog() {
  await loadFaceLibrary()
  faceDialogVisible.value = true
}

async function refreshFaces() {
  await loadFaceLibrary()
  ElMessage.success('人脸库已刷新')
}

async function captureRegister() {
  if (!registerName.value.trim()) {
    ElMessage.warning('请输入姓名')
    return
  }
  if (!running.value) {
    ElMessage.warning('请先开启摄像头再采集注册')
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
    ElMessage.success(`人脸 "${res.name}" 注册成功`)
    registerName.value = ''
    // 提示:人脸库缓存会在 Yolo TTL 到期后自动刷新(30s)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    capturing.value = false
    registerLoading.value = false
  }
}

async function deleteFace(face) {
  try {
    await ElMessageBox.confirm(`确定删除人脸 "${face.name}" 吗?`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    await removeFace(face.id)
    faceLibrary.value = faceLibrary.value.filter((f) => f.id !== face.id)
    ElMessage.success('已删除')
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
        <el-button :icon="Refresh" size="small" @click="initEndpoint" plain>重连</el-button>
        <el-button :icon="User" size="small" @click="openFaceDialog" plain>人脸库管理</el-button>
      </div>
    </div>

    <!-- 主体:左控制 + 右显示 -->
    <div class="vision-grid">
      <!-- 左栏:控制面板 -->
      <section class="panel ctrl-panel">
        <div class="panel-head">
          <span class="panel-tag label-eyebrow">Control</span>
          <h3 class="panel-title display">视觉检测控制台</h3>
        </div>

        <!-- 模式切换 -->
        <div class="mode-switch">
          <button
            class="mode-btn"
            :class="{ active: mode === 'detect' }"
            @click="switchMode('detect')"
          >
            <el-icon :size="16"><Aim /></el-icon>
            <span>目标检测</span>
          </button>
          <button
            class="mode-btn"
            :class="{ active: mode === 'recognize' }"
            @click="switchMode('recognize')"
          >
            <el-icon :size="16"><User /></el-icon>
            <span>人脸识别</span>
          </button>
        </div>

        <!-- 摄像头控制 -->
        <div class="ctrl-row">
          <el-button
            v-if="!running"
            type="primary"
            :icon="VideoPlay"
            :disabled="!yoloReady"
            @click="startCamera"
          >
            开启摄像头
          </el-button>
          <el-button
            v-else
            type="danger"
            :icon="VideoPause"
            @click="stopCamera"
          >
            停止
          </el-button>
        </div>

        <!-- 检测参数(仅目标检测模式) -->
        <div class="ctrl-block" v-if="mode === 'detect'">
          <div class="ctrl-label">
            <span>置信度阈值</span>
            <span class="mono val">{{ conf.toFixed(2) }}</span>
          </div>
          <el-slider v-model="conf" :min="0.1" :max="0.9" :step="0.05" />
        </div>

        <!-- 人脸识别提示 -->
        <div class="ctrl-block" v-if="mode === 'recognize'">
          <div class="hint-card">
            <p>当前已注册人脸:<b>{{ faceLibrary.length }}</b> 人</p>
            <p class="muted" v-if="!hasFaces">暂无人脸,请先到"人脸库管理"注册</p>
            <p class="muted" v-else>识别由 Yolo 本地比对,注册后约 30 秒生效</p>
          </div>
        </div>

        <!-- 性能指标 -->
        <div class="metrics">
          <div class="metric">
            <div class="metric-label label-eyebrow">FPS</div>
            <div class="metric-val mono">{{ fps }}</div>
          </div>
          <div class="metric">
            <div class="metric-label label-eyebrow">{{ mode === 'detect' ? '检测目标' : '识别人脸' }}</div>
            <div class="metric-val mono">{{ mode === 'detect' ? detections.length : faces.length }}</div>
          </div>
        </div>

        <!-- 离线/错误提示 -->
        <div class="err-card" v-if="errorMsg">
          <span>{{ errorMsg }}</span>
        </div>
      </section>

      <!-- 右栏:显示区 -->
      <section class="panel display-panel">
        <div class="panel-head">
          <span class="panel-tag label-eyebrow">Live</span>
          <h3 class="panel-title display">
            {{ mode === 'detect' ? '目标检测画面' : '人脸识别画面' }}
          </h3>
        </div>

        <div class="video-wrap">
          <video ref="videoRef" autoplay playsinline muted></video>
          <canvas ref="drawCanvasRef" class="overlay"></canvas>
          <!-- 隐藏的抓帧 canvas -->
          <canvas ref="canvasRef" class="hidden-canvas"></canvas>

          <!-- 占位提示 -->
          <div class="placeholder" v-if="!running">
            <el-icon :size="48"><Camera /></el-icon>
            <p>{{ yoloReady ? '点击"开启摄像头"开始' : 'Yolo 服务离线' }}</p>
          </div>
        </div>

        <!-- 结果列表 -->
        <div class="result-wrap">
          <div class="result-head label-eyebrow">
            {{ mode === 'detect' ? '检测结果' : '识别结果' }}
          </div>
          <!-- 目标检测结果 -->
          <ul class="result-list" v-if="mode === 'detect'">
            <li v-for="(d, i) in detections" :key="'d' + i" class="result-item">
              <span class="r-class">{{ d.class }}</span>
              <span class="r-conf mono">{{ (d.confidence * 100).toFixed(1) }}%</span>
              <span class="r-bbox mono">[{{ d.bbox.join(', ') }}]</span>
            </li>
            <li v-if="detections.length === 0" class="empty">暂无检测目标</li>
          </ul>
          <!-- 人脸识别结果 -->
          <ul class="result-list" v-else>
            <li v-for="(f, i) in faces" :key="'f' + i" class="result-item face">
              <span class="r-class" :class="{ known: f.name, unknown: !f.name }">
                {{ f.name || '未识别' }}
              </span>
              <span class="r-sim mono" v-if="f.name">{{ (f.similarity * 100).toFixed(1) }}%</span>
              <span class="r-bbox mono">[{{ f.bbox.join(', ') }}]</span>
            </li>
            <li v-if="faces.length === 0" class="empty">暂无识别人脸</li>
          </ul>
        </div>
      </section>
    </div>

    <!-- 人脸库管理弹窗 -->
    <el-dialog
      v-model="faceDialogVisible"
      title="人脸库管理"
      width="640px"
      :append-to-body="true"
    >
      <!-- 注册新区 -->
      <div class="reg-row">
        <el-input
          v-model="registerName"
          placeholder="输入姓名"
          maxlength="64"
          clearable
          @keyup.enter="captureRegister"
        />
        <el-button
          type="primary"
          :icon="Plus"
          :loading="registerLoading"
          :disabled="!running || !registerName.trim()"
          @click="captureRegister"
        >
          采集注册
        </el-button>
        <el-button :icon="Refresh" @click="refreshFaces" plain />
      </div>
      <p class="reg-hint" v-if="!running">
        <el-icon><VideoPlay /></el-icon>
        请先在主界面开启摄像头,再采集注册
      </p>

      <!-- 人脸库列表 -->
      <el-table :data="faceLibrary" stripe size="small" class="face-table" empty-text="暂无人脸">
        <el-table-column label="样张" width="72">
          <template #default="{ row }">
            <img
              v-if="row.sample_snapshot"
              :src="row.sample_snapshot"
              class="thumb"
              alt="snapshot"
            />
            <span v-else class="no-snap">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="姓名" />
        <el-table-column label="注册时间" width="180">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button
              :icon="Delete"
              size="small"
              type="danger"
              circle
              plain
              @click="deleteFace(row)"
            />
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
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
  border: 1px solid var(--line);
  background: var(--surface-soft);
  color: var(--ink-2);
  letter-spacing: 0.02em;
}
.badge .dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ink-4);
}
.badge.on {
  color: var(--sage-deep);
  border-color: var(--sage);
  background: var(--sage-tint);
}
.badge.on .dot {
  background: var(--sage);
  box-shadow: 0 0 8px var(--sage);
}
.badge.off {
  color: var(--terra);
  border-color: rgba(239, 107, 126, 0.4);
  background: rgba(239, 107, 126, 0.08);
}
.badge.off .dot {
  background: var(--terra);
}
.badge.ghost {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
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
.panel {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  padding: 20px 22px;
  overflow: hidden;
}
.panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 34px;
  height: 2px;
  background: var(--sage);
  opacity: 0.85;
}
.panel-head {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.panel-tag {
  display: block;
  margin-bottom: 4px;
}
.panel-title {
  margin: 0;
  font-size: 17px;
  color: var(--ink);
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
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--surface-soft);
  color: var(--ink-3);
  cursor: pointer;
  font-size: 13px;
  font-family: inherit;
  transition: all 0.2s var(--ease);
}
.mode-btn:hover {
  border-color: var(--line-strong);
  color: var(--ink-2);
}
.mode-btn.active {
  border-color: var(--sage);
  color: var(--sage-deep);
  background: var(--sage-tint);
}
.ctrl-row {
  margin-bottom: 18px;
}
.ctrl-block {
  margin-bottom: 18px;
}
.ctrl-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
  color: var(--ink-2);
  margin-bottom: 8px;
}
.ctrl-label .val {
  color: var(--sage-deep);
}
.hint-card {
  padding: 12px 14px;
  border: 1px dashed var(--line);
  border-radius: var(--radius);
  background: var(--surface-soft);
  font-size: 13px;
  color: var(--ink-2);
}
.hint-card p {
  margin: 0 0 6px;
}
.hint-card p:last-child {
  margin-bottom: 0;
}
.hint-card b {
  color: var(--sage-deep);
}
.muted {
  color: var(--ink-4);
  font-size: 12px;
}

/* ===== 性能指标 ===== */
.metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.metric {
  text-align: center;
  padding: 10px 8px;
  background: var(--surface-soft);
  border-radius: var(--radius);
  border: 1px solid var(--line);
}
.metric-label {
  font-size: 10px;
  color: var(--ink-3);
  margin-bottom: 4px;
}
.metric-val {
  font-size: 22px;
  font-weight: 600;
  color: var(--ink);
}

/* ===== 错误卡片 ===== */
.err-card {
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: var(--radius);
  border: 1px solid rgba(239, 107, 126, 0.4);
  background: rgba(239, 107, 126, 0.08);
  color: var(--terra);
  font-size: 12px;
}

/* ===== 显示面板 ===== */
.video-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: var(--paper-deep);
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--line);
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
  transform: scaleX(-1); /* 镜像,符合直觉 */
}
.video-wrap .overlay {
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
  color: var(--ink-4);
  z-index: 3;
  background: var(--paper-deep);
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
  color: var(--ink-3);
  margin-bottom: 8px;
}
.result-list {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 180px;
  overflow-y: auto;
}
.result-item {
  display: grid;
  grid-template-columns: 1.4fr 0.8fr 1.8fr;
  gap: 12px;
  padding: 8px 10px;
  font-size: 13px;
  border-bottom: 1px solid var(--line);
  align-items: center;
}
.result-item:last-child {
  border-bottom: none;
}
.result-item:hover {
  background: var(--sage-tint);
}
.r-class {
  color: var(--ink);
  font-weight: 500;
}
.r-class.known {
  color: var(--sage-deep);
}
.r-class.unknown {
  color: var(--terra);
}
.r-conf, .r-sim {
  color: var(--amber);
  font-size: 12px;
}
.r-sim {
  color: var(--sage-deep);
}
.r-bbox {
  color: var(--ink-4);
  font-size: 11px;
}
.empty {
  text-align: center;
  color: var(--ink-4);
  font-size: 12px;
  padding: 20px;
}

/* ===== 人脸库弹窗 ===== */
.reg-row {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.reg-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--amber);
  font-size: 12px;
  margin: 0 0 14px;
}
.face-table .thumb {
  width: 44px;
  height: 44px;
  object-fit: cover;
  border-radius: var(--radius);
  border: 1px solid var(--line);
}
.no-snap {
  color: var(--ink-4);
}
</style>
