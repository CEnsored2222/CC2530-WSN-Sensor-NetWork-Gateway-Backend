import req from './request'

export const listLogs = (params) => req.get('/operation-logs', { params })
export const listActions = () => req.get('/operation-logs/actions')
export const deleteLog = (id) => req.delete(`/operation-logs/${id}`)
export const deleteLogsBatch = (ids) => req.delete('/operation-logs', { data: { ids } })
