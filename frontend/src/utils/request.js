import axios from 'axios'
import { ElMessage, ElNotification } from 'element-plus'

// 创建axios实例
const service = axios.create({
  baseURL: '/api',
  timeout: 60000, // 60秒超时（投递操作可能比较久）
  headers: {
    'Content-Type': 'application/json;charset=utf-8'
  }
})

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 响应拦截器
service.interceptors.response.use(
  (response) => {
    const res = response.data
    // 文件下载响应
    if (response.config.responseType === 'blob') {
      return response.data
    }
    // 统一响应格式：{ code, message, data }
    if (typeof res === 'object' && 'code' in res) {
      if (res.code === 200) {
        return res.data
      } else {
        ElMessage.error(res.message || '请求失败')
        return Promise.reject(new Error(res.message || 'Error'))
      }
    }
    return res
  },
  (error) => {
    let msg = error.message || '网络错误'
    if (error.response) {
      const { status, data } = error.response
      if (status === 401) msg = '未登录或登录已过期'
      else if (status === 403) msg = '无权限访问'
      else if (status === 404) msg = '接口不存在'
      else if (status === 500) msg = '服务器内部错误'
      if (data && data.message) msg = data.message
    }
    ElNotification({ type: 'error', title: '请求失败', message: msg, duration: 3000 })
    return Promise.reject(error)
  }
)

// 通用请求方法
export const request = service

/**
 * GET 请求
 */
export function get(url, params) {
  return service.get(url, { params })
}

/**
 * POST 请求
 */
export function post(url, data, config = {}) {
  return service.post(url, data, config)
}

/**
 * PUT 请求
 */
export function put(url, data) {
  return service.put(url, data)
}

/**
 * DELETE 请求
 */
export function del(url) {
  return service.delete(url)
}

/**
 * 文件上传
 */
export function upload(url, file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  return service.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: onProgress ? (progressEvent) => {
      const percent = Math.round((progressEvent.loaded * 100) / (progressEvent.total || 1))
      onProgress(percent)
    } : undefined
  })
}

export default service
