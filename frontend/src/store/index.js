import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as loginApi, getMe } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const saved = localStorage.getItem('userInfo')
  const userInfo = ref(saved ? JSON.parse(saved) : null)
  const token = ref(localStorage.getItem('token') || '')
  const isLoggedIn = computed(() => !!token.value)

  async function loginAction(data) {
    const res = await loginApi(data)
    token.value = res.access_token
    userInfo.value = res.user
    localStorage.setItem('userInfo', JSON.stringify(res.user))
    localStorage.setItem('token', res.access_token)
    return res.user
  }

  async function fetchMe() {
    try {
      const user = await getMe()
      userInfo.value = user
      localStorage.setItem('userInfo', JSON.stringify(user))
      return user
    } catch (e) {
      logout()
      return null
    }
  }

  function logout() {
    userInfo.value = null
    token.value = ''
    localStorage.removeItem('userInfo')
    localStorage.removeItem('token')
  }

  return { userInfo, token, isLoggedIn, loginAction, fetchMe, logout }
})

export const usePlatformStore = defineStore('platform', () => {
  const sessions = ref([])
  const currentSessionId = ref(null)

  function setSessions(list) {
    sessions.value = list
    const boss = list.find(s => s.platform === 'boss')
    if (boss) currentSessionId.value = boss.id
  }

  function getSessionByPlatform(platform = 'boss') {
    return sessions.value.find(s => s.platform === platform)
  }

  return { sessions, currentSessionId, setSessions, getSessionByPlatform }
})
