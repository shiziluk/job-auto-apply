<template>
  <el-container class="main-layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="sidebar">
      <div class="logo-area">
        <el-icon :size="28" color="#409eff"><Promotion /></el-icon>
        <span v-show="!isCollapse" class="logo-text">牛人Agent</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="false"
        router
        background-color="#001529"
        text-color="#c9d1d9"
        active-text-color="#ffffff"
        class="side-menu"
      >
        <el-menu-item v-for="item in menuList" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 主内容区 -->
    <el-container>
      <!-- 顶部导航 -->
      <el-header class="header">
        <div class="header-left">
          <el-icon class="toggle-btn" :size="20" @click="isCollapse = !isCollapse">
            <Fold v-if="!isCollapse" /><Expand v-else />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>{{ currentPageTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-tag v-if="bossLoggedIn" type="success" effect="light" round>
            <el-icon style="margin-right:4px"><CircleCheck /></el-icon>
            Boss已登录
          </el-tag>
          <el-tag v-else type="warning" effect="light" round @click="$router.push('/platform-auth')" style="cursor:pointer">
            <el-icon style="margin-right:4px"><Warning /></el-icon>
            Boss未登录
          </el-tag>
          <el-dropdown>
            <span class="user-info">
              <el-avatar :size="32" style="background:#409eff">
                {{ userInfo?.nickname?.charAt(0) || userInfo?.username?.charAt(0) || 'U' }}
              </el-avatar>
              <span class="username">{{ userInfo?.nickname || userInfo?.username || '用户' }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容区 -->
      <el-main class="main-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <!-- keep-alive：缓存页面组件实例，切换菜单后再回来可保留表单/列表/搜索状态 -->
            <keep-alive :max="10">
              <component :is="Component" />
            </keep-alive>
          </transition>
        </router-view>
      </el-main>

      <el-footer class="footer">
        <span>© 2026 牛人Agent · 智能求职投递系统（JobClaw）· 仅供个人学习使用</span>
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore, usePlatformStore } from '@/store'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const platformStore = usePlatformStore()

const isCollapse = ref(false)
const userInfo = computed(() => userStore.userInfo)
const activeMenu = computed(() => route.path)
const currentPageTitle = computed(() => route.meta?.title || '')

const bossLoggedIn = computed(() => {
  const session = platformStore.getSessionByPlatform('boss')
  return session && session.is_logged_in
})

const menuList = [
  { path: '/dashboard', title: '仪表盘', icon: 'Odometer' },
  { path: '/platform-auth', title: '平台登录', icon: 'Key' },
  { path: '/resume', title: '简历管理', icon: 'Document' },
  { path: '/job-search', title: '职位搜索', icon: 'Search' },
  { path: '/apply-tasks', title: '投递任务', icon: 'Promotion' },
  { path: '/apply-records', title: '投递记录', icon: 'Tickets' },
  { path: '/filter-rules', title: '黑白名单', icon: 'Filter' },
  { path: '/settings', title: '系统设置', icon: 'Setting' },
]

function logout() {
  userStore.logout()
  router.push('/login')
}
</script>

<style lang="scss" scoped>
.main-layout {
  height: 100vh;
}
.sidebar {
  background: #001529;
  transition: width 0.3s;
  overflow: hidden;
}
.logo-area {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #fff;
  border-bottom: 1px solid #0f2847;
}
.logo-text {
  font-size: 18px;
  font-weight: bold;
  letter-spacing: 1px;
}
.side-menu {
  border-right: none;
  height: calc(100vh - 60px);
  :deep(.el-menu-item) {
    height: 48px;
    line-height: 48px;
    &:hover { background: #112b4a; }
    &.is-active { background: #409eff !important; }
  }
}
.header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 60px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.toggle-btn {
  cursor: pointer;
  color: #606266;
  &:hover { color: #409eff; }
}
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.username {
  font-size: 14px;
  color: #303133;
}
.main-content {
  padding: 20px;
  background: #f5f7fa;
  min-height: calc(100vh - 60px - 40px);
}
.footer {
  height: 40px;
  line-height: 40px;
  text-align: center;
  font-size: 12px;
  color: #909399;
  background: #fff;
  border-top: 1px solid #e4e7ed;
}
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>