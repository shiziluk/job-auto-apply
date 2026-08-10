<template>
  <div class="dashboard">
    <!-- 数据统计卡片 -->
    <el-row :gutter="16">
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card card-blue">
          <div class="stat-icon"><el-icon :size="28"><Tickets /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ stats.totalApplied || 0 }}</div>
            <div class="stat-label">累计投递</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card card-green">
          <div class="stat-icon"><el-icon :size="28"><CircleCheck /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ stats.todayApplied || 0 }}</div>
            <div class="stat-label">今日投递</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card card-orange">
          <div class="stat-icon"><el-icon :size="28"><ChatDotRound /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ stats.replied || 0 }}</div>
            <div class="stat-label">HR回复</div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="hover" class="stat-card card-purple">
          <div class="stat-icon"><el-icon :size="28"><Trophy /></el-icon></div>
          <div class="stat-info">
            <div class="stat-num">{{ stats.interviewed || 0 }}</div>
            <div class="stat-label">面试邀约</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表 + 快捷操作 -->
    <el-row :gutter="16" class="mt-20">
      <el-col :xs="24" :lg="16">
        <el-card shadow="hover">
          <template #header>
            <div class="flex-between">
              <span>📈 最近7天投递趋势</span>
              <el-tag size="small" type="info">最近7天</el-tag>
            </div>
          </template>
          <div ref="chartRef" style="height: 300px;"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="8">
        <el-card shadow="hover">
          <template #header><span>⚡ 快捷操作</span></template>
          <div class="quick-actions">
            <el-button type="primary" size="large" @click="$router.push('/platform-auth')" class="action-btn">
              <el-icon><Key /></el-icon>&nbsp;平台登录
            </el-button>
            <el-button type="success" size="large" @click="$router.push('/resume')" class="action-btn">
              <el-icon><Upload /></el-icon>&nbsp;上传简历
            </el-button>
            <el-button type="warning" size="large" @click="$router.push('/job-search')" class="action-btn">
              <el-icon><Search /></el-icon>&nbsp;搜索职位
            </el-button>
            <el-button type="danger" size="large" @click="$router.push('/apply-tasks')" class="action-btn">
              <el-icon><Promotion /></el-icon>&nbsp;新建任务
            </el-button>
          </div>
        </el-card>

        <el-card shadow="hover" class="mt-20">
          <template #header><span>🔔 平台状态</span></template>
          <div class="platform-status">
            <div class="status-item">
              <div class="flex-between">
                <span class="platform-name">Boss直聘</span>
                <el-tag :type="bossSession?.is_logged_in ? 'success' : 'danger'" effect="light" round>
                  {{ bossSession?.is_logged_in ? '已登录' : '未登录' }}
                </el-tag>
              </div>
              <p class="text-muted" style="font-size:12px;margin:4px 0 0;">
                {{ bossSession?.account_name || '未绑定账号' }}
                <span v-if="bossSession?.last_check_at"> · 检测于{{ formatTime(bossSession.last_check_at) }}</span>
              </p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近投递记录 -->
    <el-card shadow="hover" class="mt-20">
      <template #header>
        <div class="flex-between">
          <span>📋 最近投递记录</span>
          <el-button text type="primary" @click="$router.push('/apply-records')">查看全部 →</el-button>
        </div>
      </template>
      <el-table :data="recentRecords" stripe v-loading="loading">
        <el-table-column prop="company_name" label="公司" min-width="180">
          <template #default="{ row }">
            <span class="company-name">{{ row.company_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="job_title" label="职位" min-width="160" />
        <el-table-column prop="salary_text" label="薪资" width="120">
          <template #default="{ row }">
            <span class="text-danger">
              {{ row.salary_text || (row.salary_min ? `${row.salary_min}-${row.salary_max}K` : '-') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="100" />
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status==='success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.status==='failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="row.status==='skipped'" type="info" size="small">跳过</el-tag>
            <el-tag v-else type="warning" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="投递时间" width="170">
          <template #default="{ row }">{{ formatTime(row.applied_at || row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onActivated, nextTick } from 'vue'
import * as echarts from 'echarts'
import dayjs from 'dayjs'
import { usePlatformStore } from '@/store'
import { ElMessage } from 'element-plus'
import { getApplyStats, getApplyRecords } from '@/api/apply'

const platformStore = usePlatformStore()
const loading = ref(false)
const chartRef = ref(null)
let chartInstance = null

const stats = ref({
  totalApplied: 0,
  todayApplied: 0,
  replied: 0,
  interviewed: 0
})

const recentRecords = ref([])

const bossSession = computed(() => platformStore.getSessionByPlatform('boss'))

function formatTime(t) {
  if (!t) return '-'
  return dayjs(t).format('YYYY-MM-DD HH:mm')
}

function initChart() {
  if (!chartRef.value) return
  chartInstance = echarts.init(chartRef.value)
  const days = []
  const data = []
  for (let i = 6; i >= 0; i--) {
    const d = dayjs().subtract(i, 'day')
    days.push(d.format('MM-DD'))
    data.push(0)
  }
  chartInstance.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: days },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      name: '投递数',
      type: 'line',
      smooth: true,
      data,
      areaStyle: { color: 'rgba(64,158,255,0.2)' },
      lineStyle: { color: '#409eff', width: 3 },
      itemStyle: { color: '#409eff' }
    }]
  })
  window.addEventListener('resize', () => chartInstance && chartInstance.resize())
}

async function loadData() {
  loading.value = true
  try {
    const [statsData, recordsData] = await Promise.all([
      getApplyStats().catch(() => null),
      getApplyRecords({ page: 1, page_size: 5 }).catch(() => null),
    ])
    if (statsData) {
      stats.value = {
        totalApplied: statsData.totalApplied || 0,
        todayApplied: statsData.todayApplied || 0,
        replied: statsData.replied || 0,
        interviewed: statsData.interviewed || 0,
      }
    }
    if (recordsData && recordsData.items) {
      recentRecords.value = recordsData.items
    }
  } catch (e) {
    console.error('加载数据失败:', e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadData()
  await nextTick()
  initChart()
})
// 页面被 keep-alive 缓存后，再次进入时刷新数据（首次挂载由 onMounted 负责，跳过首帧 onActivated）
let firstActivated = true
onActivated(async () => {
  if (firstActivated) {
    firstActivated = false
    return
  }
  await loadData()
  await nextTick()
  initChart()
})
</script>

<style lang="scss" scoped>
.stat-card {
  border-radius: 12px;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px;
  .stat-icon {
    width: 64px; height: 64px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    color: #fff;
  }
  .stat-num { font-size: 26px; font-weight: bold; color: #1f2937; }
  .stat-label { font-size: 13px; color: #6b7280; margin-top: 4px; }
}
.card-blue .stat-icon { background: linear-gradient(135deg,#667eea,#764ba2); }
.card-green .stat-icon { background: linear-gradient(135deg,#11998e,#38ef7d); }
.card-orange .stat-icon { background: linear-gradient(135deg,#f093fb,#f5576c); }
.card-purple .stat-icon { background: linear-gradient(135deg,#4facfe,#00f2fe); }

.quick-actions {
  display: flex; flex-direction: column; gap: 12px;
  .action-btn {
    width: 100%;
    justify-content: flex-start;
    padding: 14px 20px;
  }
}
.platform-status {
  display: flex; flex-direction: column; gap: 12px;
  .status-item {
    padding: 12px;
    background: #f8fafc;
    border-radius: 8px;
  }
  .platform-name { font-weight: 600; font-size: 14px; }
}
.company-name { font-weight: 500; }
.text-danger { color: #f56c6c; font-weight: 500; }
</style>