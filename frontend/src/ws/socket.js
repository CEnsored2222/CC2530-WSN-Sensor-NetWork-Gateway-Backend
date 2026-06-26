import { io } from 'socket.io-client'
import { useUserStore } from '@/stores/user'

let socket = null

export function getSocket() {
  if (socket) return socket
  socket = io({
    path: '/socket.io',
    transports: ['websocket', 'polling'],
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
