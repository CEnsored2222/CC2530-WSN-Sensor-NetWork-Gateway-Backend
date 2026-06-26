import req from './request'

export const login = (username, password) =>
  req.post('/auth/login', { username, password })

export const register = (username, password) =>
  req.post('/auth/register', { username, password })

export const me = () => req.get('/auth/me')
