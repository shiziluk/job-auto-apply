import { get, post } from '@/utils/request'

export function startPlatformLogin(platform) {
  return post('/platform/login/start', { platform })
}

export function getLoginStatus(taskId) {
  return get(`/platform/login/status/${taskId}`)
}

export function cancelLogin(taskId) {
  return post(`/platform/login/cancel/${taskId}`)
}

export function getPlatformSessions() {
  return get('/platform/sessions')
}

export function checkPlatformSession(sessionId) {
  return post(`/platform/session/${sessionId}/check`)
}

export function deletePlatformSession(sessionId) {
  return post(`/platform/session/${sessionId}/logout`)
}

export function getJobKeywords() {
  return get('/job/keywords')
}

export function startJobSearch(data) {
  // 多关键词/多城市搜索较慢（单次约10-30秒/组合），放宽到10分钟，避免60秒全局超时
  return post('/job/search', data, { timeout: 600000 })
}

export function startJobApply(data) {
  return post('/job/apply', data)
}

export function getApplyStatus(taskId) {
  return get(`/job/apply/status/${taskId}`)
}

export function stopApplyTask(taskId) {
  return post(`/job/apply/stop/${taskId}`)
}