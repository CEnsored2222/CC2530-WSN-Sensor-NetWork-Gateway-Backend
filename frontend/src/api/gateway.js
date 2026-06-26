import req from './request'

export const listGateways = () => req.get('/gateways')
export const listPending = () => req.get('/gateways/pending')
export const approve = (gwUuid, name) =>
  req.post(`/gateways/${gwUuid}/approve`, name ? { name } : {})
export const reject = (gwUuid) => req.post(`/gateways/${gwUuid}/reject`)
export const unbind = (gid) => req.delete(`/gateways/${gid}`)
