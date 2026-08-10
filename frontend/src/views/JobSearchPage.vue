<template>
  <div class="job-search">
    <!-- 搜索条件 -->
    <el-card shadow="hover" class="mb-20">
      <template #header><span>🔎 职位搜索条件</span></template>
      <el-form :model="searchForm" label-width="100px" :inline="true">
        <el-form-item label="平台">
          <el-select v-model="searchForm.platform" style="width:140px">
            <el-option label="Boss直聘" value="boss" />
          </el-select>
        </el-form-item>
        <el-form-item label="登录会话">
          <el-select v-model="searchForm.session_id" placeholder="请先登录平台" style="width:220px">
            <el-option
              v-for="s in platformSessions"
              :key="s.id"
              :label="`${s.platform_name} - ${s.account_name || '未登录'}`"
              :value="s.id"
              :disabled="!s.is_logged_in"
            />
          </el-select>
          <el-button v-if="!searchForm.session_id" link type="primary" @click="$router.push('/platform-auth')">
            去登录 →
          </el-button>
        </el-form-item>
        <el-form-item label="关键词">
          <el-select
            v-model="searchForm.keywords"
            multiple
            filterable
            allow-create
            default-first-option
            placeholder="输入关键词后回车添加，可多选"
            style="width:360px"
          >
            <el-option v-for="k in keywordSuggestions" :key="k" :label="k" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="城市">
          <el-select v-model="searchForm.city_code" multiple placeholder="不限（可多选，多城市会逐个搜索后合并）" style="width:220px">
            <el-option label="深圳" value="101280600" />
            <el-option label="广州" value="101280100" />
            <el-option label="北京" value="101010100" />
            <el-option label="上海" value="101020100" />
            <el-option label="杭州" value="101210100" />
            <el-option label="成都" value="101270100" />
            <el-option label="武汉" value="101200100" />
            <el-option label="西安" value="101110100" />
            <el-option label="南京" value="101190100" />
            <el-option label="重庆" value="101040100" />
            <el-option label="苏州" value="101190400" />
            <el-option label="长沙" value="101250100" />
          </el-select>
        </el-form-item>
        <el-form-item label="薪资范围">
          <el-input-number v-model="searchForm.salary_min" :min="0" :max="100" placeholder="最低" style="width:110px" />
          <span style="margin:0 6px">-</span>
          <el-input-number v-model="searchForm.salary_max" :min="0" :max="200" placeholder="最高" style="width:110px" />
          <span style="margin-left:4px;color:#909399">K</span>
        </el-form-item>
        <el-form-item label="经验">
          <el-select v-model="searchForm.experience" multiple placeholder="不限（可多选）" style="width:220px">
            <el-option label="应届生" :value="1" />
            <el-option label="1年以内" :value="2" />
            <el-option label="1-3年" :value="3" />
            <el-option label="3-5年" :value="4" />
            <el-option label="5-10年" :value="5" />
            <el-option label="10年以上" :value="6" />
          </el-select>
        </el-form-item>
        <el-form-item label="学历">
          <el-select v-model="searchForm.education" multiple placeholder="不限（可多选）" style="width:200px">
            <el-option label="大专" :value="1" />
            <el-option label="本科" :value="2" />
            <el-option label="硕士" :value="3" />
            <el-option label="博士" :value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="公司规模">
          <el-select v-model="searchForm.company_scales" multiple placeholder="不限（可多选）" style="width:220px">
            <el-option label="0-20人" :value="1" />
            <el-option label="20-99人" :value="2" />
            <el-option label="100-499人" :value="3" />
            <el-option label="500-999人" :value="4" />
            <el-option label="1000-9999人" :value="5" />
            <el-option label="10000人以上" :value="6" />
          </el-select>
        </el-form-item>
        <el-form-item label="休息制度">
          <el-select v-model="searchForm.rest_policy" multiple placeholder="不限（可多选，勾选后严格过滤并自动补详情页确认）" style="width:240px">
            <el-option label="双休" value="双休" />
            <el-option label="大小周" value="大小周" />
            <el-option label="单休" value="单休" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doSearch" :loading="searching">
            <el-icon><Search /></el-icon>&nbsp;搜索职位
          </el-button>
          <el-button @click="resetForm">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 操作栏 -->
    <el-card shadow="hover" class="mb-20" v-if="jobList.length > 0">
      <div class="flex-between">
        <div class="select-info">
          <el-checkbox v-model="selectAll" :indeterminate="isIndeterminate" @change="onSelectAll">全选</el-checkbox>
          <span class="text-muted" style="margin:0 12px">
            共 <b class="text-primary">{{ jobList.length }}</b> 个职位，已选 <b class="text-warning">{{ selectedJobs.length }}</b> 个
            <span v-if="alreadyAppliedCount">，已投递跳过 <b class="text-danger">{{ alreadyAppliedCount }}</b> 个</span>
          </span>
          <el-tag type="success" effect="light" size="small">白名单优先: {{ whitelistCount }}</el-tag>
          <el-tag type="danger" effect="light" size="small" style="margin-left:6px">黑名单过滤: {{ blacklistCount }}</el-tag>
        </div>
        <div>
          <div class="quota-bar" v-if="quota">
            <span>今日打招呼：已用 <b>{{ quota.todaySuccess }}</b> / {{ quota.dailyLimit }}</span>
            <span :class="quota.remaining <= 10 ? 'text-danger' : 'text-primary'">剩余 <b>{{ quota.remaining }}</b> 个</span>
          </div>
          <el-select v-model="applyResumeId" placeholder="选择简历（可跳过）" style="width:200px;margin-right:10px" clearable>
            <el-option label="不使用简历（仅打招呼）" :value="0" />
            <el-option v-for="r in resumeList" :key="r.id"
              :label="`${r.resume_name}${r.is_default?' (默认)':''}`"
              :value="r.id" />
          </el-select>
          <el-select v-model="applyMode" style="width:140px;margin-right:10px">
            <el-option label="半自动（确认后投）" value="semi" />
            <el-option label="全自动（直接投）" value="auto" />
          </el-select>
          <el-button type="danger" :disabled="selectedJobs.length === 0" :loading="applying" @click="confirmApply">
            <el-icon><Promotion /></el-icon>&nbsp;批量投递（{{ selectedJobs.length }}）
          </el-button>
        </div>
      </div>
      <div v-if="applyProgress" class="apply-progress mt-10">
        <el-progress
          :percentage="applyPercent"
          :status="applyStatusType"
          :stroke-width="14"
          style="width:420px"
        />
        <span class="text-muted" style="margin-left:12px">
          {{ applyProgress.current || 0 }}/{{ applyProgress.total || 0 }}
          · 成功 {{ applyProgress.success || 0 }}
          · 失败 {{ applyProgress.failed || 0 }}
          · 跳过 {{ applyProgress.skipped || 0 }}
        </span>
        <el-button v-if="applyTaskId" size="small" link type="primary" @click="$router.push('/apply-tasks')">查看任务</el-button>
        <el-button v-if="applyProgress.status === 'running'" size="small" link type="danger" @click="stopApply">停止</el-button>
      </div>
    </el-card>

    <!-- 职位列表 -->
    <el-card shadow="hover">
      <template #header>
        <div class="flex-between">
          <span>📋 职位列表</span>
          <div>
            <el-button size="small" :disabled="pageNo<=1" @click="pageNo--;doSearch()">上一页</el-button>
            <span style="margin:0 8px">第 {{ pageNo }} 页</span>
            <el-button size="small" @click="pageNo++;doSearch()">下一页</el-button>
          </div>
        </div>
      </template>

      <el-table :data="jobList" stripe v-loading="searching" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="50" :selectable="(r)=>!r.is_applied" />
        <el-table-column label="公司/职位" min-width="280">
          <template #default="{ row }">
            <div class="job-title">
              <el-link type="primary" :href="row.job_url" target="_blank">{{ row.job_title }}</el-link>
              <el-tag v-if="row.is_headhunter" type="danger" effect="light" size="small">猎头</el-tag>
              <el-tag v-if="row.is_internship" type="warning" effect="light" size="small">实习</el-tag>
              <el-tag v-if="row.is_applied" type="info" size="small">已投</el-tag>
            </div>
            <div class="company-name">
              <el-icon><OfficeBuilding /></el-icon>&nbsp;
              {{ row.company_name || '-' }}
              <span class="text-muted" style="margin-left:8px">{{ row.company_size }} · {{ row.company_industry }}</span>
            </div>
            <div class="tags mt-10" v-if="row.tags && row.tags.length">
              <el-tag v-for="t in row.tags.slice(0,5)" :key="t" size="small" effect="plain" style="margin-right:4px">{{ t }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="薪资" width="140">
          <template #default="{ row }">
            <span class="salary-text">{{ row.salary_text || (row.salary_min?`${row.salary_min}-${row.salary_max}K`:'面议') }}</span>
          </template>
        </el-table-column>
        <el-table-column label="城市/区域" width="130">
          <template #default="{ row }">
            <span>{{ row.city }}<span v-if="row.area"> · {{ row.area }}</span></span>
          </template>
        </el-table-column>
        <el-table-column label="经验/学历" width="140">
          <template #default="{ row }">
            <span>{{ row.experience || '不限' }} / {{ row.education || '不限' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="休息" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.rest_policy === '双休'" type="success" size="small">双休</el-tag>
            <el-tag v-else-if="row.rest_policy === '大小周'" type="warning" size="small">大小周</el-tag>
            <el-tag v-else-if="row.rest_policy === '单休'" type="danger" size="small">单休</el-tag>
            <span v-else class="text-muted">未知</span>
          </template>
        </el-table-column>
        <el-table-column label="HR活跃" width="120" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.hr_active_days != null" :content="`${row.hr_active_days===0?'今日':row.hr_active_days+'天前'}活跃`">
              <el-tag :type="row.hr_active_days <= 3 ? 'success' : (row.hr_active_days <= 7 ? 'warning' : 'info')" size="small">
                {{ row.hr_active_text || (row.hr_active_days===0?'今日':row.hr_active_days+'天前') }}
              </el-tag>
            </el-tooltip>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="匹配说明" min-width="160">
          <template #default="{ row }">
            <el-tag v-if="row.match_reason && row.match_reason.includes('白名单')" type="success" effect="light" size="small">
              {{ row.match_reason }}
            </el-tag>
            <el-tag v-else-if="row.match_reason && row.match_reason.includes('黑名单')" type="danger" effect="light" size="small">
              {{ row.match_reason }}
            </el-tag>
            <span v-else class="text-muted">{{ row.match_reason || '正常匹配' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!searching && jobList.length === 0" description="暂无搜索结果，请调整搜索条件后重试" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { usePlatformStore } from '@/store'
import { startJobSearch, startJobApply, getApplyStatus, stopApplyTask, getJobKeywords } from '@/api/platform'
import { getApplyStats } from '@/api/apply'
import { getResumeList, setDefaultResume } from '@/api/resume'

const platformStore = usePlatformStore()
const searching = ref(false)
const applying = ref(false)
const pageNo = ref(1)
const searchForm = reactive({
  platform: 'boss',
  session_id: null,
  keywords: ['AI 应用工程师'],
  city_code: [],
  salary_min: null,
  salary_max: null,
  experience: [],
  education: [],
  company_scales: [],
  rest_policy: [],
  page: 1,
  page_size: 30,
})
const keywordSuggestions = ref(['AI 应用工程师', 'AI 应用开发', 'AI 应用开发工程师', 'AI Agent 开发', 'AI Agent 工程师', '大模型应用开发', '大模型应用工程师'])
const quota = ref(null)
const jobList = ref([])
const selectedJobs = ref([])
const selectAll = ref(false)
const isIndeterminate = ref(false)
const resumeList = ref([])
const applyResumeId = ref(null)
const applyMode = ref('semi')
let applyPollTimer = null
const applyTaskId = ref(null)
const applyProgress = ref(null)

const platformSessions = computed(() => platformStore.sessions)
const alreadyAppliedCount = computed(() => jobList.value.filter(j => j.is_applied).length)
const whitelistCount = ref(0)
const blacklistCount = ref(0)
const applyPercent = computed(() => {
  const p = applyProgress.value
  if (!p || !p.total) return 0
  return Math.min(100, Math.round(((p.current || 0) / p.total) * 100))
})
const applyStatusType = computed(() => {
  const st = applyProgress.value && applyProgress.value.status
  if (st === 'done') return 'success'
  if (st === 'failed' || st === 'stopped') return 'exception'
  return undefined
})

function resetForm() {
  Object.assign(searchForm, {
    keywords: ['AI 应用工程师'], city_code: [],
    salary_min: null, salary_max: null,
    experience: [], education: [], company_scales: [], rest_policy: []
  })
}

async function doSearch() {
  if (!searchForm.session_id) {
    ElMessage.warning('请先选择已登录的平台会话，或先去平台登录页面扫码登录')
    return
  }
  if (!searchForm.keywords || searchForm.keywords.length === 0) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searching.value = true
  try {
    const data = await startJobSearch({
      session_id: searchForm.session_id,
      platform: searchForm.platform,
      keywords: searchForm.keywords,
      city_code: searchForm.city_code,
      salary_min: searchForm.salary_min,
      salary_max: searchForm.salary_max,
      experience: searchForm.experience,
      education: searchForm.education,
      company_scales: searchForm.company_scales,
      rest_policy: searchForm.rest_policy,
      page: pageNo.value,
      page_size: 30,
    })
    jobList.value = data.jobs || data
    whitelistCount.value = jobList.value.filter(j => j.match_reason && j.match_reason.includes('白名单')).length
    blacklistCount.value = jobList.value.filter(j => j.match_reason && j.match_reason.includes('黑名单')).length
    ElMessage.success(`搜索完成，共找到 ${jobList.value.length} 个职位`)
  } catch(e) {
    ElMessage.error('搜索失败：' + (e.message || '未知错误'))
  } finally {
    searching.value = false
  }
}

function onSelectionChange(rows) {
  selectedJobs.value = rows
  const selectableCount = jobList.value.filter(j => !j.is_applied).length
  selectAll.value = rows.length > 0 && rows.length === selectableCount
  isIndeterminate.value = rows.length > 0 && rows.length < selectableCount
}
function onSelectAll(val) {
}

async function confirmApply() {
  const noResume = !applyResumeId.value || applyResumeId.value === 0
  const resumeTip = noResume ? '\n（未选择简历，将仅发送打招呼，不关联简历）' : ''
  let quotaTip = ''
  if (quota.value && selectedJobs.value.length > quota.value.remaining) {
    quotaTip = `\n\n⚠️ 今日剩余打招呼名额仅 ${quota.value.remaining} 个，本次选中的 ${selectedJobs.value.length} 个职位只会投到名额用完为止。`
  }
  const mode = await ElMessageBox.confirm(
    `即将投递 ${selectedJobs.value.length} 个职位，是否继续？${resumeTip}${quotaTip}`,
    '确认投递',
    {
      distinguishCancelAndClose: true,
      confirmButtonText: '确认投递',
      cancelButtonText: '取消',
      type: 'warning'
    }
  ).catch(() => null)
  if (mode !== 'confirm') return

  applying.value = true
  try {
    // 根据搜索关键词自动判断投递方向：AI/开发类关键词 → 严格标题终检；销售/产品经理等 → 宽松
    const kwJoined = (Array.isArray(searchForm.keywords) ? searchForm.keywords.join(' ') : String(searchForm.keywords || '')).toLowerCase()
    const isAiDev = /开发|工程师|算法|研发|大模型|agent|智能体|应用工程|rag/.test(kwJoined) && !/销售|产品经理|运营|客服|顾问|市场|专员|助理|管培/.test(kwJoined)
    const titleFilter = isAiDev ? 'strict' : 'loose'
    const resp = await startJobApply({
      session_id: searchForm.session_id,
      platform: searchForm.platform,
      title_filter: titleFilter,
      jobs: selectedJobs.value.map(j => ({
        platform: j.platform || searchForm.platform || 'boss',
        job_id: j.job_id,
        job_title: j.job_title,
        job_url: j.job_url,
        company_id: j.company_id,
        company_name: j.company_name,
        company_size: j.company_size,
        company_industry: j.company_industry,
        salary_min: j.salary_min,
        salary_max: j.salary_max,
        city: j.city,
        area: j.area,
        experience: j.experience,
        education: j.education,
        hr_name: j.hr_name,
        hr_title: j.hr_title,
        hr_active_days: j.hr_active_days,
        is_headhunter: j.is_headhunter,
      })),
      resume_id: applyResumeId.value ? applyResumeId.value : null,
      greeting_template: '您好，$company的$HR您好，我对$position岗位很感兴趣，我的简历已附上，期待您的回复！',
    })
    ElMessage.success('投递任务已启动')
    applyTaskId.value = resp && resp.task_id ? resp.task_id : null
    if (applyTaskId.value) {
      applyProgress.value = {
        task_id: applyTaskId.value, status: 'running',
        total: resp.total || selectedJobs.value.length, current: 0,
        success: 0, failed: 0, skipped: 0, error: null,
      }
      stopApplyPolling()
      await pollApplyProgress()
      applyPollTimer = setInterval(pollApplyProgress, 2000)
    } else {
      applyProgress.value = null
      ElMessage.info('任务已启动，请到"投递任务"页面查看进度')
    }
  } catch(e) {
    ElMessage.error('投递失败：' + (e.message || '未知错误'))
  } finally {
    applying.value = false
  }
}

async function pollApplyProgress() {
  if (!applyTaskId.value) return
  try {
    const data = await getApplyStatus(applyTaskId.value)
    applyProgress.value = data
    const finished = ['done', 'failed', 'stopped'].includes(data.status)
    if (finished) {
      stopApplyPolling()
      loadQuota()
      if (data.status === 'done') {
        const quotaMsg = data.message && data.message.includes('名额') ? '，' + data.message : ''
        ElMessage.success(`投递完成：成功 ${data.success}，失败 ${data.failed}，跳过 ${data.skipped}${quotaMsg}`)
      } else if (data.status === 'failed') {
        ElMessage.error('投递任务失败：' + (data.error || '未知错误'))
      } else if (data.status === 'stopped') {
        ElMessage.warning('投递任务已停止')
      }
    }
  } catch(e) {
    // 任务不存在（404）或网络异常：停止轮询
    stopApplyPolling()
    applyProgress.value = null
  }
}

function stopApplyPolling() {
  if (applyPollTimer) {
    clearInterval(applyPollTimer)
    applyPollTimer = null
  }
}

async function stopApply() {
  if (!applyTaskId.value) return
  try {
    await stopApplyTask(applyTaskId.value)
    ElMessage.warning('已发送停止信号')
  } catch(e) {
    ElMessage.error('停止失败：' + (e.message || '未知错误'))
  }
}

async function loadSessions() {
  try {
    const list = await getPlatformSessions()
    platformStore.setSessions(list)
    const bossSession = list.find(s => s.platform === 'boss' && s.is_logged_in)
    if (bossSession) {
      searchForm.session_id = bossSession.id
    }
  } catch(e) {
    console.error(e)
  }
}

async function loadResumes() {
  try {
    const data = await getResumeList({ page: 1, page_size: 100 })
    resumeList.value = data.items || []
    const defaultResume = resumeList.value.find(r => r.is_default)
    if (defaultResume) {
      applyResumeId.value = defaultResume.id
    } else if (resumeList.value.length > 0) {
      applyResumeId.value = resumeList.value[0].id
    }
  } catch(e) {
    console.error(e)
  }
}

async function loadKeywordSuggestions() {
  try {
    const data = await getJobKeywords()
    if (data && data.suggestions && data.suggestions.length) {
      keywordSuggestions.value = data.suggestions
    }
  } catch(e) {
    console.error('加载关键词词表失败', e)
  }
}

async function loadQuota() {
  try {
    const data = await getApplyStats()
    quota.value = data
  } catch(e) {
    console.error('加载剩余名额失败', e)
  }
}

onMounted(async () => {
  await loadSessions()
  await loadResumes()
  loadKeywordSuggestions()
  loadQuota()
})

onUnmounted(() => {
  stopApplyPolling()
})
</script>

<style lang="scss" scoped>
.mb-20 { margin-bottom: 20px; }
.mt-10 { margin-top: 8px; }
.text-muted { color: #909399; font-size: 12px; }
.text-primary { color: #409eff; }
.text-warning { color: #e6a23c; }
.text-danger { color: #f56c6c; }
.job-title {
  font-size: 15px; font-weight: 600; margin-bottom: 6px;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.company-name { font-size: 13px; color: #606266; }
.tags { display: flex; flex-wrap: wrap; }
.salary-text {
  color: #f56c6c; font-weight: bold; font-size: 15px;
}
.select-info { display: flex; align-items: center; }
.quota-bar {
  font-size: 13px; color: #606266; margin-bottom: 8px;
  display: flex; gap: 14px; align-items: center;
}
</style>
