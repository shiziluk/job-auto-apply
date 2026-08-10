<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-title">
        <el-icon :size="40" color="#409eff"><Promotion /></el-icon>
        <h1>牛人Agent</h1>
        <p class="sub-title">求职者的智能助手 · 对标 HR Agent · 自动抓取匹配一键投递</p>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px" class="login-form">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" size="large">
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" size="large" show-password @keyup.enter="handleLogin">
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.remember">记住我</el-checkbox>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" class="w-100" :loading="loading" @click="handleLogin">
            登录系统
          </el-button>
        </el-form-item>
      </el-form>

      <div class="tips">
        <el-alert type="info" :closable="false" show-icon>
          <p>💡 初始账号：admin / admin123</p>
          <p>登录后请及时修改密码，随后对接Boss直聘扫码登录</p>
        </el-alert>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const formRef = ref()
const loading = ref(false)

const form = reactive({
  username: 'admin',
  password: 'admin123',
  remember: true
})

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function handleLogin() {
  try {
    await formRef.value.validate()
  } catch { return }
  
  loading.value = true
  try {
    await userStore.loginAction({ username: form.username, password: form.password })
    ElMessage.success('登录成功')
    router.push(route.query.redirect || '/dashboard')
  } catch (e) {
    // request.js 拦截器已统一处理错误提示
  } finally {
    loading.value = false
  }
}
</script>

<style lang="scss" scoped>
.login-page {
  height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.login-card {
  width: 100%;
  max-width: 460px;
  background: #fff;
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}
.login-title {
  text-align: center;
  margin-bottom: 30px;
  h1 {
    font-size: 26px;
    margin: 10px 0 6px;
    color: #1f2937;
  }
  .sub-title {
    font-size: 13px;
    color: #6b7280;
    margin: 0;
  }
}
.login-form {
  margin-top: 10px;
}
.w-100 {
  width: 100%;
}
.tips {
  margin-top: 20px;
  font-size: 12px;
  :deep(p) { margin: 2px 0; }
}
</style>
