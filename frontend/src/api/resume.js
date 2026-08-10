import { get, post, put, del, upload } from '@/utils/request'

export function getResumeList(params) {
  return get('/resumes', params)
}

export function uploadResume(file, onProgress) {
  return upload('/resume/upload', file, onProgress)
}

export function createResume(data) {
  return post('/resume', data)
}

export function updateResume(id, data) {
  return put(`/resume/${id}`, data)
}

export function deleteResume(id) {
  return post(`/resume/${id}/delete`)
}

export function setDefaultResume(id) {
  return post(`/resume/${id}/default`)
}
