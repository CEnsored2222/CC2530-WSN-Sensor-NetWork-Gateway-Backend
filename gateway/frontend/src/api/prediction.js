import req from './request'

// 触发预测(即时训练+预测)
export const runPrediction = (data) => req.post('/predictions/run', data)

// 某设备某指标最新预测
export const latestPrediction = (params) => req.get('/predictions/latest', { params })

// 历史预测列表
export const predictionHistory = (params) => req.get('/predictions/history', { params })

// ===== MLP ONNX 管线 =====

// MLP 预训练(同步,实测 1-3s)
export const mlpTrain = (data) => req.post('/predictions/mlp/train', data)

// MLP 手动微调(异步,返回 202)
export const mlpFinetune = (data) => req.post('/predictions/mlp/finetune', data)

// MLP 手动评估(同步,需先微调产生 eval_set)
export const mlpEvaluate = (data) => req.post('/predictions/mlp/evaluate', data)

// MLP 模型状态(单个)
export const mlpStatus = (params) => req.get('/predictions/mlp/status', { params })

// MLP 评估记录列表
export const mlpEvaluations = (params) => req.get('/predictions/mlp/evaluations', { params })

// MLP 所有模型列表
export const mlpModels = () => req.get('/predictions/mlp/models')
