import { ref, onMounted, onBeforeUnmount, shallowRef } from 'vue'
import { getSocket, connectSocket } from '@/ws/socket'

/**
 * 实时数据 composable:封装 socket.js
 * 用法:
 *   const { data, status } = useRealtimeData('sensor_data')
 *   // data 为最新一条事件负载,status 为连接状态
 */
export function useRealtimeData(eventName) {
  const data = shallowRef(null)
  const status = ref('disconnected') // connected | connecting | disconnected

  let socket = null

  function onEvent(payload) {
    data.value = payload
  }

  function onConnect() { status.value = 'connected' }
  function onDisconnect() { status.value = 'disconnected' }
  function onConnectError() { status.value = 'connecting' }

  onMounted(() => {
    socket = getSocket()
    connectSocket()
    socket.on(eventName, onEvent)
    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)
    socket.on('connect_error', onConnectError)
    if (socket.connected) status.value = 'connected'
    else status.value = 'connecting'
  })

  onBeforeUnmount(() => {
    if (socket) {
      socket.off(eventName, onEvent)
      socket.off('connect', onConnect)
      socket.off('disconnect', onDisconnect)
      socket.off('connect_error', onConnectError)
    }
  })

  return { data, status }
}
