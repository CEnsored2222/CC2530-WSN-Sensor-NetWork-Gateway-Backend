import req from './request'

export const login = (username, password) =>
  req.post('/auth/login', { username, password })

export const register = (username, password, email, code, token) =>
  req.post('/auth/register', { username, password, email, code, token })

export const sendCode = (email) =>
  req.post('/auth/send-code', { email })

export const me = () => req.get('/auth/me')
