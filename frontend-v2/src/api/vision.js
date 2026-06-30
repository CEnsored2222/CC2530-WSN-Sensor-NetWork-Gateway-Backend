// 视觉模块后端 API 封装(走 Atmos 后端,带 JWT)
// 设计文档第 6.3 节接口清单(链路 [2]):
//   GET    /api/vision/endpoint        获取 Yolo 公网地址
//   GET    /api/vision/faces           当前用户人脸库列表
//   POST   /api/vision/faces           人脸注册(frame+name → 后端调 Yolo 提特征 → 存库)
//   DELETE /api/vision/faces/{id}      删除人脸(仅本人)
import req from './request'

export const getEndpoint = () => req.get('/vision/endpoint')

export const listFaces = () => req.get('/vision/faces')

export const addFace = (data) => req.post('/vision/faces', data)

export const removeFace = (id) => req.delete(`/vision/faces/${id}`)
