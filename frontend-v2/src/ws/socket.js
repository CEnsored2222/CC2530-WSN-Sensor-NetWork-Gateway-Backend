import { io } from 'socket.io-client'
import { useUserStore } from '@/stores/user'

let socket = null

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
  // 此处仅做日志,保留控制台可见性便于调试
  socket.on('connect_error', (err) => {
    // 静默处理: 失效 sid 是预期行为,控制台已由 socket.io 自身打印
    // 避免 console.error 重复噪声
    if (import.meta.env.DEV) {
      console.debug('[socket] connect_error (will auto-recover):', err.message)
    }
  })

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
}
