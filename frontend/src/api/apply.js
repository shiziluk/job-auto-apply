import { get, post, put } from '@/utils/request'

export function getApplyStats() {
  return get('/apply/stats')
}

export function getApplyRecords(params) {
  return get('/apply/records', params)
}

export function getApplyTasks(params) {
  return get('/apply/tasks', params)
}

export function createApplyTask(data) {
  return post('/apply/task', data)
}

export function updateApplyTask(id, data) {
  return put(`/apply/task/${id}`, data)
}

export function deleteApplyTask(id) {
  return post(`/apply/task/${id}/delete`)
}

export function updateApplyRecordFollow(id, data) {
  return put(`/apply/record/${id}/follow`, data)
}


export function runFollowup(data = {}) {
  // 跟进扫描可能较久（登录/滑块等待），超时放宽到5分钟
  return post('/apply/followup/run', data, { timeout: 300000 })
}

export function getFollowupStatus() {
  return get('/apply/followup/status')
}
