<template>
  <div class="records-page">
    <el-card shadow="hover" class="mb-20">
      <template #header>
        <div class="flex-between">
          <span>🔍 投递记录筛选</span>
          <div class="header-actions">
            <span v-if="followStatus.error" class="follow-tip">{{ followStatus.error }}</span>
            <el-button type="success" :loading="followRunning" @click="runFollow">🤖 自动跟进</el-button>
            <el-button @click="exportData"><el-icon><Download /></el-icon>&nbsp;导出记录</el-button>
          </div>
        </div>
      </template>
      <el-form :inline="true" :model="filter" label-width="80px">
        <el-form-item label="平台">
          <el-select v-model="filter.platform" clearable style="width:130px">
            <el-option label="Boss直聘" value="boss" />
          </el-select>
        </el-form-item>
        <el-form-item label="投递状态">
          <el-select v-model="filter.status" clearable style="width:130px">
            <el-option label="投递成功" value="success" />
            <el-option label="投递失败" value="failed" />
            <el-option label="跳过" value="skipped" />
          </el-select>
        </el-form-item>
        <el-form-item label="跟进状态">
          <el-select v-model="filter.followStatus" clearable style="width:130px">
            <el-option label="无回复" value="none" />
            <el-option label="HR已回复" value="replied" />
            <el-option label="已约面" value="interviewed" />
            <el-option label="已拒" value="rejected" />
            <el-option label="已拿Offer" value="offer" />
          </el-select>
        </el-form-item>
        <el-form-item label="关键词">
          <el-input v-model="filter.keyword" placeholder="搜索公司名/职位" style="width:220px" clearable />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filter.dateRange" type="daterange"
            start-placeholder="开始日期" end-placeholder="结束日期"
            value-format="YYYY-MM-DD" style="width:260px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadData">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="hover">
      <el-table :data="records" stripe v-loading="loading">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="company_name" label="公司" min-width="160">
          <template #default="{ row }">
            <span class="company-name" @click="openJob(row)">{{ row.company_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="job_title" label="职位" min-width="150" />
        <el-table-column label="薪资" width="130">
          <template #default="{ row }">
            <span class="text-danger">
              {{ row.salary_text || (row.salary_min ? `${row.salary_min}-${row.salary_max}K` : '-') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="city" label="城市" width="80" />
        <el-table-column prop="hr_name" label="HR" width="100">
          <template #default="{ row }">
            <span>{{ row.hr_name || '-' }}<span v-if="row.is_headhunter===1" class="text-danger" style="margin-left:4px">（猎头）</span></span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="投递状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status==='success'" type="success" size="small">成功</el-tag>
            <el-tag v-else-if="row.status==='failed'" type="danger" size="small">失败</el-tag>
            <el-tag v-else-if="row.status==='skipped'" type="info" size="small">跳过</el-tag>
            <el-tag v-else type="warning" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="follow_up_status" label="跟进状态" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.follow_up_status"
              size="small" style="width:100px"
              @change="updateFollow(row)"
            >
              <el-option label="无回复" value="none" />
              <el-option label="HR已回复" value="replied" />
              <el-option label="已约面" value="interviewed" />
              <el-option label="已拒" value="rejected" />
              <el-option label="已拿Offer" value="offer" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="follow_up_remark" label="跟进备注" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="remark-cell">{{ row.follow_up_remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="applied_at" label="投递时间" width="160">
          <template #default="{ row }">{{ formatTime(row.applied_at || row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openJob(row)">打开</el-button>
            <el-button type="danger" link size="small" @click="deleteRow(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination mt-20">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onActivated, onDeactivated, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import { getApplyRecords, updateApplyRecordFollow, runFollowup, getFollowupStatus } from '@/api/apply'

const loading = ref(false)
const records = ref([])
const filter = reactive({ platform: '', status: '', followStatus: '', keyword: '', dateRange: [] })
const pagination = reactive({ page: 1, pageSize: 20, total: 0 })
const followRunning = ref(false)
const followStatus = ref({})

async function loadData() {
  loading.value = true
  try {
    const params = {
      page: pagination.page,
      page_size: pagination.pageSize,
    }
    if (filter.platform) params.platform = filter.platform
    if (filter.status) params.status = filter.status
    if (filter.followStatus) params.follow_status = filter.followStatus
    if (filter.keyword) params.keyword = filter.keyword
    
    const data = await getApplyRecords(params)
    records.value = data.items || []
    pagination.total = data.total || 0
  } catch(e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function resetFilter() {
  Object.assign(filter, { platform: '', status: '', followStatus: '', keyword: '', dateRange: [] })
  pagination.page = 1
  loadData()
}

function openJob(row) {
  if (row.job_url) {
    window.open(row.job_url, '_blank')
  } else {
    ElMessage.info('职位链接不存在')
  }
}

async function deleteRow(row) {
  await ElMessageBox.confirm('确定删除这条投递记录吗？', '提示', { type: 'warning' })
  ElMessage.success('已删除')
  loadData()
}

async function updateFollow(row) {
  try {
    await updateApplyRecordFollow(row.id, { follow_up_status: row.follow_up_status })
    ElMessage.success('跟进状态已更新')
  } catch(e) {
    ElMessage.error('更新失败')
  }
}

function exportData() {
  ElMessage.info('导出功能待对接后端')
}

function formatTime(t) {
  return t ? dayjs(t).format('YYYY-MM-DD HH:mm') : '-'
}

// ===== 自动跟进 =====
async function runFollow() {
  followRunning.value = true
  try {
    // force=true：用户手动点击=强制重新检测（忽略后台风控冷却，解封后立即生效）
    const data = await runFollowup({ session_id: 1, force: true })
    followStatus.value = data || {}
    if (data && data.error) {
      ElMessage.warning(data.error)
    } else {
      ElMessage.success(`跟进完成：匹配${data.matched || 0}条，更新${data.updated || 0}条`)
    }
    loadData()
  } catch (e) {
    // 拦截器已统一提示
  } finally {
    followRunning.value = false
    loadFollowStatus()
  }
}

async function loadFollowStatus() {
  try {
    followStatus.value = (await getFollowupStatus()) || {}
  } catch (e) {
    /* 忽略，后台未启动时静默 */
  }
}

// ===== 页面轮询：后台自动跟进更新后，前端自动同步显示 =====
let pollTimer = null
function startPolling() {
  stopPolling()
  pollTimer = setInterval(() => {
    loadData()
    loadFollowStatus()
  }, 60000)
}
function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  loadData()
  loadFollowStatus()
  startPolling()
})
// keep-alive 缓存后，再次进入时刷新列表并恢复轮询（首次挂载由 onMounted 负责）
let firstActivated = true
onActivated(() => {
  if (firstActivated) {
    firstActivated = false
    return
  }
  loadData()
  loadFollowStatus()
  startPolling()
})
onDeactivated(stopPolling)
onBeforeUnmount(stopPolling)
</script>

<style lang="scss" scoped>
.mb-20 { margin-bottom: 20px; }
.mt-20 { margin-top: 20px; }
.text-danger { color: #f56c6c; font-weight: 500; }
.company-name { cursor: pointer; font-weight: 500; &:hover { color: #409eff; } }
.pagination { display: flex; justify-content: flex-end; }
.header-actions { display: flex; align-items: center; gap: 10px; }
.follow-tip { color: #e6a23c; font-size: 12px; max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remark-cell { color: #909399; font-size: 12px; }
</style>