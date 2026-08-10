<template>
  <div>
    <el-card shadow="hover" v-for="page in placeholderPages" :key="page.key" class="mb-20">
      <template #header>
        <div class="flex-between">
          <span>{{ page.icon }} {{ page.title }}</span>
          <el-tag type="info">MVP后续完善</el-tag>
        </div>
      </template>
      <el-empty :description="page.desc">
        <el-button type="primary" @click="go(page.path)">先去其他页面逛逛</el-button>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
const route = useRoute()
const router = useRouter()

const pageMap = {
  '/apply-tasks': {
    key: 'tasks', icon: '📋', title: '投递任务管理',
    desc: '在这里可以创建定时/循环的投递任务，让系统按配置自动跑',
    path: '/job-search'
  },
  '/filter-rules': {
    key: 'filter', icon: '⚖️', title: '黑白名单管理',
    desc: '配置黑名单（外包/猎头/996等）和白名单（心仪公司优先投）',
    path: '/dashboard'
  },
  '/settings': {
    key: 'settings', icon: '⚙️', title: '系统设置',
    desc: '配置投递频率、每日上限、通知渠道（邮件/钉钉/飞书/Telegram）等',
    path: '/platform-auth'
  }
}
const placeholderPages = computed(() => [pageMap[route.path] || { key: 'default', icon: '📄', title: '页面开发中', desc: '敬请期待', path: '/dashboard' }])
function go(path) { router.push(path) }
</script>

<style scoped>
.mb-20 { margin-bottom: 20px; }
</style>
