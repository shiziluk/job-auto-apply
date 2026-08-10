import { createRouter, createWebHashHistory } from 'vue-router'
import MainLayout from '@/layout/MainLayout.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginPage.vue'),
    meta: { title: '登录', noAuth: true }
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/DashboardPage.vue'),
        meta: { title: '仪表盘', icon: 'Odometer' }
      },
      {
        path: 'platform-auth',
        name: 'PlatformAuth',
        component: () => import('@/views/PlatformAuthPage.vue'),
        meta: { title: '平台登录', icon: 'Key' }
      },
      {
        path: 'resume',
        name: 'Resume',
        component: () => import('@/views/ResumePage.vue'),
        meta: { title: '简历管理', icon: 'Document' }
      },
      {
        path: 'job-search',
        name: 'JobSearch',
        component: () => import('@/views/JobSearchPage.vue'),
        meta: { title: '职位搜索', icon: 'Search' }
      },
      {
        path: 'apply-tasks',
        name: 'ApplyTasks',
        component: () => import('@/views/ApplyTasksPage.vue'),
        meta: { title: '投递任务', icon: 'Promotion' }
      },
      {
        path: 'apply-records',
        name: 'ApplyRecords',
        component: () => import('@/views/ApplyRecordsPage.vue'),
        meta: { title: '投递记录', icon: 'Tickets' }
      },
      {
        path: 'filter-rules',
        name: 'FilterRules',
        component: () => import('@/views/_PlaceholderPage.vue'),
        meta: { title: '黑白名单', icon: 'Filter' }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/_PlaceholderPage.vue'),
        meta: { title: '系统设置', icon: 'Setting' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  }
})

// 路由守卫：简单检查本地是否有用户信息
router.beforeEach((to, from, next) => {
  const userInfo = localStorage.getItem('userInfo')
  if (to.meta.noAuth) {
    next()
  } else if (!userInfo) {
    next({ path: '/login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} - 牛人Agent` : '牛人Agent - 智能求职投递系统'
})

export default router
