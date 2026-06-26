import req from './request'

// 触发预测(即时训练+预测)
export const runPrediction = (data) => req.post('/predictions/run', data)

// 某设备某指标最新预测
export const latestPrediction = (params) => req.get('/predictions/latest', { params })

// 历史预测列表
export const predictionHistory = (params) => req.get('/predictions/history', { params })
