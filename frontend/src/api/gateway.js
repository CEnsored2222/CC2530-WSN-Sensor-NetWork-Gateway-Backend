import req from './request'

export const listGateways = () => req.get('/gateways')
export const listAllGateways = () => req.get('/gateways/all')
export const listPending = () => req.get('/gateways/pending')
export const approve = (gwUuid) =>
  req.post(`/gateways/${gwUuid}/approve`)
export const bindGateway = (gwUuid, name) =>
  req.post(`/gateways/${gwUuid}/bind`, name ? { name } : {})
export const reject = (gwUuid) => req.post(`/gateways/${gwUuid}/reject`)
export const unbind = (gid) => req.delete(`/gateways/${gid}`)
export const renameGateway = (gid, name) => req.patch(`/gateways/${gid}`, { name })
