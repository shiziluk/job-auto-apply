<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <div class="flex-between">
          <span>📋 投递任务</span>
          <el-button type="primary" size="small" @click="goSearch">发起新投递</el-button>
        </div>
      </template>

      <el-table :data="tasks" stripe v-loading="loading">
        <el-table-column label="ID" width="70" prop="id" />
        <el-table-column label="任务名称" min-width="220" prop="task_name" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusMeta(row).type" size="small">{{ statusMeta(row).label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" min-width="280">
          <template #default="{ row }">
            <div v-if="row.progress && row.progress.total" class="progress-cell">
              <el-progress
                :percentage="percentOf(row)"
                :status="progressStatus(row)"
                :stroke-width="10"
                style="width:180px"
              />
              <span class="text-muted" style="margin-left:8px">
                {{ row.progress.current || 0 }}/{{ row.progress.total }}
                · 成功 {{ row.progress.success || 0 }}
                · 失败 {{ row.progress.failed || 0 }}
                · 跳过 {{ row.progress.skipped || 0 }}
              </span>
            </div>
            <span v-else class="text-muted">
              累计投递 {{ row.total_applied || 0 }}（成功 {{ row.total_success || 0 }} / 失败 {{ row.total_failed || 0 }}）
            </span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="上次运行" width="160">
          <template #default="{ row }">{{ row.last_run_at ? fmtTime(row.last_run_at) : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button v-if="row.status === 'running'" size="small" type="warning" @click="stopTask(row)">停止</el-button>
            <el-button size="small" type="danger" @click="removeTask(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && tasks.length === 0" description="暂无投递任务，去职位搜索页发起一次投递吧" />

      <div class="pager" v-if="total > pageSize">
        <el-pagination
          layout="prev, pager, next, total"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="onPageChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getApplyTasks, deleteApplyTask } from '@/api/apply'
import { getApplyStatus, stopApplyTask } from '@/api/platform'

const router = useRouter()
const tasks = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(20)
const total = ref(0)
let pollTimer = null

const statusMap = {
  draft: { label: '草稿', type: 'info' },
  running: { label: '进行中', type: 'primary' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  paused: { label: '已停止', type: 'warning' },
  stopped: { label: '已停止', type: 'warning' },
}

function statusMeta(row) {
  const key = row.status || 'draft'
  return statusMap[key] || { label: key, type: 'info' }
}

function percentOf(row) {
  const p = row.progress
  if (!p || !p.total) return 0
  return Math.min(100, Math.round(((p.current || 0) / p.total) * 100))
}

function progressStatus(row) {
  const st = row.progress && row.progress.status
  if (st === 'done') return 'success'
  if (st === 'failed' || st === 'stopped') return 'exception'
  return undefined
}

function fmtTime(v) {
  if (!v) return '-'
  const d = new Date(v)
  if (isNaN(d.getTime())) return String(v)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadTasks() {
  loading.value = true
  try {
    const data = await getApplyTasks({ page: page.value, page_size: pageSize.value })
    tasks.value = (data && data.items) || []
    total.value = (data && data.total) || 0
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function refreshRunning() {
  // 刷新所有进行中任务的实时进度
  for (const row of tasks.value) {
    if (row.status !== 'running') continue
    try {
      const data = await getApplyStatus(row.id)
      if (data) {
        row.progress = data
        if (data.status === 'done') row.status = 'completed'
        else if (data.status === 'failed') row.status = 'failed'
        else if (data.status === 'stopped') row.status = 'paused'
      }
    } catch (e) {
      // 任务已结束或进程重启，忽略
    }
  }
}

async function stopTask(row) {
  try {
    await stopApplyTask(row.id)
    ElMessage.warning('已发送停止信号')
    await loadTasks()
  } catch (e) {
    ElMessage.error('停止失败：' + (e.message || '未知错误'))
  }
}

async function removeTask(row) {
  const ok = await ElMessageBox.confirm(
    `确定删除投递任务「${row.task_name}」？关联的投递记录会保留。`,
    '删除确认',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  ).catch(() => false)
  if (!ok) return
  try {
    await deleteApplyTask(row.id)
    ElMessage.success('已删除')
    await loadTasks()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.message || '未知错误'))
  }
}

function onPageChange(p) {
  page.value = p
  loadTasks()
}

function goSearch() {
  router.push('/job-search')
}

// 多标签页场景：页面重新可见时刷新任务列表（避免切回旧标签页看到过期空数据）
function handleVisibility() {
  if (document.visibilityState === 'visible') {
    loadTasks()
    refreshRunning()
  }
}

onMounted(async () => {
  await loadTasks()
  await refreshRunning()
  // 每8秒全量刷新任务列表：覆盖多标签页切回场景（旧标签页也能自动更新）
  pollTimer = setInterval(() => {
    loadTasks()
    refreshRunning()
  }, 8000)
  document.addEventListener('visibilitychange', handleVisibility)
})

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  document.removeEventListener('visibilitychange', handleVisibility)
})
</script>

<style scoped>
.flex-between { display: flex; align-items: center; justify-content: space-between; }
.progress-cell { display: flex; align-items: center; }
.text-muted { color: #909399; font-size: 12px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
