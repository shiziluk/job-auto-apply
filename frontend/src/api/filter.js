/**
 * 过滤规则（黑白名单）相关API
 */
import { get, post, put, del } from '@/utils/request'

// 规则列表
export function getFilterRules(params = {}) {
  return get('/filter/rules', params)
}

// 创建规则
export function createFilterRule(data) {
  return post('/filter/rule', data)
}

// 更新规则
export function updateFilterRule(id, data) {
  return put(`/filter/rule/${id}`, data)
}

// 删除规则
export function deleteFilterRule(id) {
  return del(`/filter/rule/${id}`)
}

// 切换启用/禁用
export function toggleFilterRule(id, enabled) {
  return post(`/filter/rule/${id}/toggle`, { enabled })
}
