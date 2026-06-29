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
    autoConnect: false
  })
  return socket
}

export function connectSocket() {
  const userStore = useUserStore()
  const s = getSocket()
  if (!userStore.token) return s
  s.auth = { token: userStore.token }
  if (!s.connected) s.connect()
  s.off('connect')
  s.on('connect', () => {
    s.emit('join', { token: userStore.token })
  })
  return s
}

export function disconnectSocket() {
  if (socket) {
    socket.removeAllListeners()
    socket.disconnect()
    socket = null
  }
}
