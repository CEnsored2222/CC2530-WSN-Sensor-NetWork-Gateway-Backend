import req from './request'

export const listLogs = (params) => req.get('/operation-logs', { params })
export const listActions = () => req.get('/operation-logs/actions')
