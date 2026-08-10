<template>
  <div class="platform-auth">
    <el-row :gutter="16">
      <!-- 平台列表 -->
      <el-col :xs="24" :lg="10">
        <el-card shadow="hover">
          <template #header>
            <div class="flex-between">
              <span>🔐 招聘平台登录</span>
              <el-button type="primary" :disabled="isLogging" @click="startLogin('boss')">
                <el-icon v-if="!isLogging"><Refresh /></el-icon>
                <el-icon v-else class="is-loading"><Loading /></el-icon>
                &nbsp;Boss直聘扫码登录
              </el-button>
            </div>
          </template>

          <div class="platform-list">
            <!-- Boss直聘 -->
            <div class="platform-item" :class="{ active: bossSession?.is_logged_in }">
              <div class="platform-logo boss-logo">BOSS</div>
              <div class="platform-info">
                <div class="platform-name">
                  Boss直聘
                  <el-tag v-if="bossSession?.is_logged_in" type="success" effect="dark" size="small" style="margin-left:8px">已登录</el-tag>
                  <el-tag v-else type="info" size="small" style="margin-left:8px">未登录</el-tag>
                </div>
                <div class="platform-account">
                  <template v-if="bossSession?.is_logged_in">
                    <span>账号：{{ bossSession.account_name || '已绑定' }}</span>
                    <span class="divider">·</span>
                    <span>上次检测：{{ formatTime(bossSession.last_check_at) }}</span>
                  </template>
                  <template v-else>
                    <span class="text-muted">点击右上角按钮进行扫码登录</span>
                  </template>
                </div>
              </div>
              <div class="platform-actions">
                <el-button v-if="bossSession?.is_logged_in" size="small" @click="checkSession('boss')">
                  检测有效性
                </el-button>
                <el-button v-if="bossSession?.is_logged_in" size="small" type="danger" @click="logoutPlatform('boss')">
                  退出登录
                </el-button>
              </div>
            </div>

            <!-- 其他平台（后续扩展） -->
            <div class="platform-item disabled">
              <div class="platform-logo lagou-logo">拉勾</div>
              <div class="platform-info">
                <div class="platform-name">
                  拉勾网
                  <el-tag type="info" size="small" style="margin-left:8px">即将上线</el-tag>
                </div>
                <div class="platform-account text-muted">规划中...</div>
              </div>
            </div>
            <div class="platform-item disabled">
              <div class="platform-logo job51-logo">51JOB</div>
              <div class="platform-info">
                <div class="platform-name">
                  前程无忧
                  <el-tag type="info" size="small" style="margin-left:8px">即将上线</el-tag>
                </div>
                <div class="platform-account text-muted">规划中...</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 登录状态/说明 -->
      <el-col :xs="24" :lg="14">
        <!-- 扫码登录弹窗 -->
        <el-card shadow="hover" v-if="isLogging">
          <template #header>
            <div class="flex-between">
              <span>📱 Boss直聘扫码登录中...（{{ countdown }}s）</span>
              <el-button type="danger" text @click="cancelLogin">取消登录</el-button>
            </div>
          </template>

          <div class="qr-login-box">
            <div class="qr-area">
              <div v-if="loginStatus.status === 'waiting'" class="qr-placeholder">
                <el-icon :size="100" color="#409eff"><Monitor /></el-icon>
                <p class="text-primary" style="font-size:15px;font-weight:600;margin-top:15px">
                  浏览器已自动打开Boss直聘登录页面
                </p>
                <p class="text-muted" style="margin-top:8px">请在弹出的浏览器中完成扫码登录...</p>
                <p style="margin-top:20px;font-size:12px;color:#909399">
                  <el-icon><Warning /></el-icon>
                  温馨提示：首次使用请务必在弹出的浏览器中手动操作，
                  Cookie会自动保存，后续无需重复登录
                </p>
              </div>
              <div v-else-if="loginStatus.status === 'logged_in'" class="login-success">
                <el-icon :size="80" color="#67c23a"><CircleCheckFilled /></el-icon>
                <p style="font-size:18px;color:#67c23a;margin-top:15px;font-weight:600">登录成功！</p>
                <p class="text-muted" style="margin-top:8px">{{ loginStatus.message }}</p>
              </div>
              <div v-else-if="loginStatus.status === 'failed'" class="login-failed">
                <el-icon :size="80" color="#f56c6c"><CircleCloseFilled /></el-icon>
                <p style="font-size:18px;color:#f56c6c;margin-top:15px;font-weight:600">登录失败</p>
                <p class="text-muted" style="margin-top:8px">{{ loginStatus.message }}</p>
              </div>
              <div v-else-if="loginStatus.status === 'timeout'" class="login-timeout">
                <el-icon :size="80" color="#e6a23c"><Clock /></el-icon>
                <p style="font-size:18px;color:#e6a23c;margin-top:15px;font-weight:600">登录超时</p>
                <p class="text-muted" style="margin-top:8px">请重新发起登录</p>
              </div>
            </div>

            <el-progress
              :percentage="Math.min(100, (180 - countdown) / 180 * 100)"
              :stroke-width="8"
              :show-text="false"
              style="margin-top:20px"
            />
          </div>
        </el-card>

        <!-- Cookie说明 -->
        <el-card shadow="hover" v-else>
          <template #header><span>💡 使用说明 & 注意事项</span></template>
          <el-steps :active="3" finish-status="success" simple>
            <el-step title="启动浏览器" description="点击上方登录按钮" />
            <el-step title="扫码登录" description="在弹出的浏览器中手动扫码" />
            <el-step title="自动保存" description="Cookie自动保存，后续复用" />
            <el-step title="开始投递" description="去职位搜索页面开始投递" />
          </el-steps>

          <el-alert type="warning" :closable="false" show-icon style="margin-top:24px">
            <div class="tips-box">
              <p><b>🔒 关于账号安全：</b></p>
              <p>1. 所有登录操作都在<span class="text-primary">你本地的浏览器</span>中完成，程序只保存Cookie到本地数据库</p>
              <p>2. Cookie<span class="text-danger">不会上传</span>到任何第三方服务器，仅在你本机使用</p>
              <p>3. 建议使用保守投递策略（默认），避免频繁操作触发风控</p>
              <br>
              <p><b>⚠️ Boss直聘每日限制：</b></p>
              <p>1. 普通用户每日约 <b class="text-warning">100次</b> 打招呼机会（新用户更少）</p>
              <p>2. 系统默认限制每日 <b class="text-primary">80次</b> 投递，留余量更安全</p>
              <p>3. 遇到验证码/滑块时会自动暂停，需你手动处理后继续</p>
            </div>
          </el-alert>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'
import { usePlatformStore } from '@/store'
import {
  startPlatformLogin, getLoginStatus, getPlatformSessions,
  checkPlatformSession, deletePlatformSession, cancelLogin as cancelLoginApi,
} from '@/api/platform'

const platformStore = usePlatformStore()

const isLogging = ref(false)
const countdown = ref(180)
const loginTaskId = ref(null)
const loginStatus = ref({ status: 'waiting', message: '' })
let pollTimer = null
let countdownTimer = null

const bossSession = computed(() => platformStore.getSessionByPlatform('boss'))

function formatTime(t) {
  if (!t) return '-'
  return dayjs(t).format('MM-DD HH:mm')
}

async function loadSessions() {
  try {
    const list = await getPlatformSessions()
    platformStore.setSessions(list)
  } catch(e) {
    console.error(e)
  }
}

async function startLogin(platform = 'boss') {
  if (isLogging.value) return
  isLogging.value = true
  countdown.value = 180
  loginStatus.value = { status: 'waiting', message: '' }

  try {
    const res = await startPlatformLogin(platform)
    loginTaskId.value = res.task_id

    ElMessage.success('已启动浏览器，请在弹出的窗口中完成扫码登录')

    countdownTimer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        cancelLogin()
        loginStatus.value = { status: 'timeout', message: '登录超时' }
      }
    }, 1000)

    pollTimer = setInterval(async () => {
      try {
        const status = await getLoginStatus(loginTaskId.value)
        loginStatus.value = status
        if (['logged_in', 'failed', 'timeout'].includes(status.status)) {
          clearInterval(pollTimer)
          clearInterval(countdownTimer)
          pollTimer = null
          countdownTimer = null
          await loadSessions()
          setTimeout(() => { isLogging.value = false }, 2000)
        }
      } catch(e) {
        console.error(e)
      }
    }, 3000)
  } catch(e) {
    ElMessage.error('启动登录失败：' + (e.message || '未知错误'))
    isLogging.value = false
  }
}

async function cancelLogin() {
  if (loginTaskId.value) {
    try { await cancelLoginApi(loginTaskId.value) } catch(e) {}
  }
  clearInterval(pollTimer)
  clearInterval(countdownTimer)
  pollTimer = null
  countdownTimer = null
  isLogging.value = false
  loginTaskId.value = null
}

async function checkSession() {
  if (!bossSession.value?.id) return
  try {
    const res = await checkPlatformSession(bossSession.value.id)
    if (res.is_logged_in) {
      ElMessage.success(res.message || '会话有效')
    } else {
      ElMessage.warning(res.message || '会话已失效')
    }
    await loadSessions()
  } catch(e) {
    ElMessage.error(e.message || '检测失败')
  }
}

async function logoutPlatform() {
  if (!bossSession.value?.id) return
  try {
    await deletePlatformSession(bossSession.value.id)
    ElMessage.success('已退出登录')
    await loadSessions()
  } catch(e) {
    ElMessage.error(e.message || '操作失败')
  }
}

onMounted(loadSessions)
onUnmounted(cancelLogin)
</script>

<style lang="scss" scoped>
.platform-list {
  display: flex; flex-direction: column; gap: 12px;
}
.platform-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: #f8fafc;
  border-radius: 12px;
  border: 2px solid transparent;
  transition: all 0.2s;
  &.active {
    border-color: #409eff;
    background: #ecf5ff;
  }
  &.disabled {
    opacity: 0.5;
  }
  &:not(.disabled):hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
  }
}
.platform-logo {
  width: 52px; height: 52px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: bold; font-size: 14px;
  flex-shrink: 0;
}
.boss-logo { background: linear-gradient(135deg, #14b8a6, #0ea5e9); }
.lagou-logo { background: linear-gradient(135deg, #3b82f6, #8b5cf6); }
.job51-logo { background: linear-gradient(135deg, #f97316, #ef4444); font-size: 13px; }
.platform-info { flex: 1; min-width: 0; }
.platform-name { font-size: 15px; font-weight: 600; color: #1f2937; }
.platform-account { font-size: 12px; color: #6b7280; margin-top: 4px; }
.divider { margin: 0 6px; color: #d1d5db; }
.platform-actions { display: flex; gap: 8px; }

.qr-login-box {
  min-height: 380px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 20px;
}
.qr-area {
  text-align: center;
  padding: 30px;
  background: linear-gradient(135deg, #f8fafc, #e0f2fe);
  border-radius: 16px;
  min-width: 400px;
}
.login-success, .login-failed, .login-timeout {
  animation: bounceIn 0.6s;
}
@keyframes bounceIn {
  0% { transform: scale(0.6); opacity: 0; }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); opacity: 1; }
}

.tips-box {
  :deep(p) { margin: 4px 0; font-size: 13px; line-height: 1.7; }
}
.text-primary { color: #409eff; font-weight: 500; }
.text-danger { color: #f56c6c; font-weight: 500; }
.text-warning { color: #e6a23c; font-weight: 500; }
.text-muted { color: #909399; }
</style>
