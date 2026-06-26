import req from './request'

export const listDevices = (gwId) => req.get(`/gateways/${gwId}/devices`)
export const bindDevice = (did, data) => req.patch(`/devices/${did}`, data)
export const deviceStream = (did) => req.get(`/devices/${did}/stream`)
export const sendCmd = (did, cmd, value) =>
  req.post(`/devices/${did}/cmd`, { cmd, value })
