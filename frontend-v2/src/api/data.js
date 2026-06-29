import req from './request'

export const realtime = () => req.get('/data/realtime')
export const history = (params) => req.get('/data/history', { params })
export const overview = () => req.get('/data/overview')
