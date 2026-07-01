import req from './request'

// 规则
export const listRules = () => req.get('/alerts/rules')
export const createRule = (data) => req.post('/alerts/rules', data)
export const updateRule = (id, data) => req.patch(`/alerts/rules/${id}`, data)
export const deleteRule = (id) => req.delete(`/alerts/rules/${id}`)
export const toggleRule = (id, enabled) => req.patch(`/alerts/rules/${id}/toggle`, { enabled })

// 告警记录
export const listRecords = (params) => req.get('/alerts/records', { params })

// 统计
export const alertStats = () => req.get('/alerts/stats')
