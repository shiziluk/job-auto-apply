<template>
  <div class="resume-page">
    <el-card shadow="hover">
      <template #header>
        <div class="flex-between">
          <span>📄 我的简历（支持多份简历切换）</span>
          <el-upload
            :show-file-list="false"
            accept=".pdf,.doc,.docx"
            :before-upload="beforeUpload"
            :http-request="handleUpload"
          >
            <el-button type="primary" :loading="uploading">
              <el-icon><Upload /></el-icon>&nbsp;上传简历
            </el-button>
          </el-upload>
        </div>
      </template>

      <el-table :data="resumeList" stripe v-loading="loading">
        <el-table-column prop="resume_name" label="简历名称" min-width="180">
          <template #default="{ row }">
            <el-input v-if="row.editing" v-model="row.resume_name" size="small" @keyup.enter="saveEdit(row)" />
            <span v-else class="resume-name" @dblclick="row.editing = true">{{ row.resume_name }}</span>
            <el-tag v-if="row.is_default" type="success" effect="dark" size="small" style="margin-left:8px">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件" width="300">
          <template #default="{ row }">
            <span class="text-muted" style="margin-right:8px">
              <el-icon><Document /></el-icon>&nbsp;{{ row.file_name || '-' }}
            </span>
            <span v-if="row.file_size" class="text-muted">{{ formatSize(row.file_size) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="target_position" label="目标岗位" width="140">
          <template #default="{ row }">
            <el-input v-if="row.editing" v-model="row.target_position" size="small" placeholder="如：后端开发" />
            <span v-else>{{ row.target_position || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="target_city" label="期望城市" width="100">
          <template #default="{ row }">
            <el-input v-if="row.editing" v-model="row.target_city" size="small" placeholder="如：深圳" />
            <span v-else>{{ row.target_city || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期望薪资" width="140">
          <template #default="{ row }">
            <span v-if="row.salary_min || row.salary_max" class="text-danger">
              {{ row.salary_min || '?' }}-{{ row.salary_max || '?' }}K
            </span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="上传时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <template v-if="row.editing">
              <el-button type="primary" link size="small" @click="saveEdit(row)">保存</el-button>
              <el-button link size="small" @click="cancelEdit(row)">取消</el-button>
            </template>
            <template v-else>
              <el-button v-if="!row.is_default" type="success" link size="small" @click="setDefault(row)">设为默认</el-button>
              <el-button type="primary" link size="small" @click="row.editing = true">编辑</el-button>
              <el-button type="primary" link size="small" @click="downloadResume(row)">下载</el-button>
              <el-button type="danger" link size="small" @click="deleteResume(row)">删除</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && resumeList.length === 0" description="暂无简历，点击右上角上传按钮上传你的简历吧~" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import {
  getResumeList, uploadResume, createResume, updateResume,
  deleteResume as deleteResumeApi, setDefaultResume,
} from '@/api/resume'

const loading = ref(false)
const uploading = ref(false)
const resumeList = ref([])
const currentPage = ref(1)
const totalPages = ref(0)
const total = ref(0)

async function loadData() {
  loading.value = true
  try {
    const data = await getResumeList({ page: currentPage.value, page_size: 10 })
    resumeList.value = data.items || []
    total.value = data.total || 0
    totalPages.value = data.total_pages || 0
  } catch(e) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function beforeUpload(file) {
  const types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
  if (!types.includes(file.type) && !/\.(pdf|doc|docx)$/i.test(file.name)) {
    ElMessage.error('仅支持 PDF/Word 格式')
    return false
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }
  return true
}

async function handleUpload({ file }) {
  uploading.value = true
  try {
    const uploadRes = await uploadResume(file, (p) => console.log('上传进度', p))
    const savedPath = uploadRes.saved_path

    await createResume({
      resume_name: file.name.replace(/\.[^.]+$/, ''),
      file_path: savedPath,
      file_name: file.name,
      file_size: uploadRes.file_size,
      file_type: uploadRes.file_type,
      target_position: '',
      target_city: '',
      is_default: resumeList.value.length === 0,
    })
    ElMessage.success('上传成功！可双击修改简历名称和目标信息')
    await loadData()
  } catch(e) {
    ElMessage.error('上传失败：' + (e.message || '未知错误'))
  } finally {
    uploading.value = false
  }
}

async function saveEdit(row) {
  try {
    await updateResume(row.id, {
      resume_name: row.resume_name,
      target_position: row.target_position,
      target_city: row.target_city,
      salary_min: row.salary_min,
      salary_max: row.salary_max,
    })
    row.editing = false
    ElMessage.success('已保存')
  } catch(e) {
    ElMessage.error('保存失败')
  }
}

function cancelEdit(row) {
  row.editing = false
}

async function setDefault(row) {
  try {
    await setDefaultResume(row.id)
    ElMessage.success('已设为默认简历')
    await loadData()
  } catch(e) {
    ElMessage.error('操作失败')
  }
}

async function deleteResume(row) {
  try {
    await ElMessageBox.confirm(`确定删除简历「${row.resume_name}」吗？`, '提示', { type: 'warning' })
    await deleteResumeApi(row.id)
    ElMessage.success('已删除')
    await loadData()
  } catch(e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

function downloadResume(row) {
  if (row.file_path) {
    window.open(`/uploads/${row.file_path}`, '_blank')
  } else {
    ElMessage.info('文件路径不存在')
  }
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(2) + 'MB'
}

function formatTime(t) {
  if (!t) return '-'
  return dayjs(t).format('YYYY-MM-DD HH:mm')
}

onMounted(loadData)
// keep-alive 缓存后，再次进入时刷新列表（首次挂载由 onMounted 负责）
let firstActivated = true
onActivated(() => {
  if (firstActivated) {
    firstActivated = false
    return
  }
  loadData()
})
</script>

<style lang="scss" scoped>
.resume-name {
  cursor: pointer;
  font-weight: 500;
  &:hover { color: #409eff; }
}
.text-danger { color: #f56c6c; font-weight: 500; }
.text-muted { color: #909399; font-size: 13px; }
</style>