import { io } from 'socket.io-client'
import { useUserStore } from '@/stores/user'

let socket = null
// pywebview 备选方案状态:SocketIO 直连失败累计次数 / ws_bridge 是否已启用
let connectErrorCount = 0
let wsBridgeActive = false

export function getSocket() {
  if (socket) return socket
  socket = io({
    path: '/socket.io',
    // 后端 Flask-SocketIO 使用 threading async_mode,仅支持 long-polling 传输。
    // 若开启 websocket 升级,Werkzeug 无法处理协议升级会抛
    // "write() before start_response" 500,故此处只保留 polling。
    transports: ['polling'],
    autoConnect: false,
    // 失效 sid 自动恢复: 服务端重启/会话过期时,客户端会用旧 sid 轮询
    // 导致 net::ERR_ABORTED 循环。以下配置确保优雅恢复:
    reconnection: true,
    reconnectionAttempts: Infinity, // 持续重连直到成功或登出
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000, // 退避上限 5s,避免轰炸服务端
    randomizationFactor: 0.5
  })

  // connect_error 触发场景: 服务端拒绝旧 sid / 401 / 网络中断
  // socket.io v4 在 connect_error 时会自动清 sid 并重连,无需手动干预
  socket.on('connect_error', (err) => {
    // 静默处理: 失效 sid 是预期行为,控制台已由 socket.io 自身打印
    // 避免 console.error 重复噪声
    if (import.meta.env.DEV) {
      console.debug('[socket] connect_error (will auto-recover):', err.message)
    }
    // pywebview 桌面环境:file:// 协议下 SocketIO 直连可能受限,
    // 累计失败 3 次后启用 Python ws_bridge 备选方案
    if (window.pywebview?.api?.ws_bridge_start) {
      connectErrorCount++
      if (connectErrorCount >= 3 && !wsBridgeActive) {
        try {
          window.pywebview.api.ws_bridge_start()
          wsBridgeActive = true
          if (import.meta.env.DEV) console.debug('[socket] ws_bridge fallback started')
        } catch (e) {}
      }
    }
  })

  // 直连恢复后停止 ws_bridge 备选方案,避免重复事件
  socket.on('connect', () => {
    connectErrorCount = 0
    if (wsBridgeActive && window.pywebview?.api?.ws_bridge_stop) {
      try {
        window.pywebview.api.ws_bridge_stop()
      } catch (e) {}
      wsBridgeActive = false
    }
  })

  // pywebview ws_bridge 备选方案:Python 侧收到服务端事件后通过此全局函数推送。
  // 此处仅做本地分发到 socket.on 注册的监听器(不发送到服务端):
  // socket.emit 会发往服务端,故借用父类 Emitter.prototype.emit 仅触发本地监听。
  window.__wsBridgePush = (event, data) => {
    if (!socket) return
    const emitterProto = Object.getPrototypeOf(Object.getPrototypeOf(socket))
    if (emitterProto && typeof emitterProto.emit === 'function') {
      emitterProto.emit.call(socket, event, data)
    }
  }

  return socket
}

function _onSocketConnect() {
  const userStore = useUserStore()
  if (userStore.token) {
    getSocket().emit('join', { token: userStore.token })
  }
}

export function connectSocket() {
  const userStore = useUserStore()
  const s = getSocket()
  if (!userStore.token) return s
  s.auth = { token: userStore.token }
  if (!s.connected) s.connect()
  s.off('connect', _onSocketConnect)
  s.on('connect', _onSocketConnect)
  return s
}

export function disconnectSocket() {
  if (socket) {
    socket.removeAllListeners()
    socket.disconnect()
    socket = null
  }
  // pywebview 环境:登出/离开登录页时停止 ws_bridge 备选方案,避免泄漏
  if (wsBridgeActive && window.pywebview?.api?.ws_bridge_stop) {
    try { window.pywebview.api.ws_bridge_stop() } catch (e) {}
  }
  wsBridgeActive = false
  connectErrorCount = 0
  // 清理全局桥接函数
  if (window.__wsBridgePush) delete window.__wsBridgePush
}
