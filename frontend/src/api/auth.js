import { get, post } from '@/utils/request'

export function login(data) {
  return post('/auth/login', null, { params: data })
}

export function register(data) {
  return post('/auth/register', null, { params: data })
}

export function getMe() {
  return get('/auth/me')
}

export function initAdmin(data) {
  return post('/auth/init-admin', null, { params: data })
}

export function changePassword(data) {
  return post('/auth/change-password', null, { params: data })
}
