<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="login-title">DemandHub 需求管理系统</h2>
      <p class="login-sub">创金合信基金零售业务线</p>

      <!-- 账密登录 -->
      <el-form v-if="!mustChange" ref="loginFormRef" :model="loginForm" :rules="loginRules" @submit.prevent>
        <el-form-item prop="loginName">
          <el-input v-model="loginForm.loginName" size="large" placeholder="登录账号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            size="large"
            placeholder="密码"
            show-password
            :prefix-icon="Lock"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doLogin">
          登录
        </el-button>
      </el-form>

      <!-- 首登强制改密 -->
      <template v-else>
        <el-alert
          type="warning"
          :closable="false"
          title="首次登录或密码已被重置，请设置新密码"
          class="change-tip"
        />
        <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" @submit.prevent>
          <el-form-item prop="oldPassword">
            <el-input
              v-model="pwdForm.oldPassword"
              type="password"
              size="large"
              placeholder="原密码"
              show-password
              :prefix-icon="Lock"
            />
          </el-form-item>
          <el-form-item prop="newPassword">
            <el-input
              v-model="pwdForm.newPassword"
              type="password"
              size="large"
              placeholder="新密码（至少 8 位，含字母和数字）"
              show-password
              :prefix-icon="Lock"
            />
          </el-form-item>
          <el-form-item prop="confirmPassword">
            <el-input
              v-model="pwdForm.confirmPassword"
              type="password"
              size="large"
              placeholder="确认新密码"
              show-password
              :prefix-icon="Lock"
              @keyup.enter="doChangePassword"
            />
          </el-form-item>
          <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doChangePassword">
            确认修改
          </el-button>
          <el-button size="large" class="login-btn cancel-btn" @click="backToLogin">返回登录</el-button>
        </el-form>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/modules/user'
import { login, changePassword } from '@/api/auth'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const mustChange = ref(false)

const loginFormRef = ref<FormInstance>()
const loginForm = reactive({ loginName: '', password: '' })
const loginRules: FormRules = {
  loginName: [{ required: true, message: '请输入登录账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const pwdFormRef = ref<FormInstance>()
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const pwdRules: FormRules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    {
      pattern: /^(?=.*[a-zA-Z])(?=.*\d).{8,}$/,
      message: '密码需至少 8 位且包含字母和数字',
      trigger: 'blur'
    }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_r, v: string, cb) => (v === pwdForm.newPassword ? cb() : cb(new Error('两次输入的密码不一致'))),
      trigger: 'blur'
    }
  ]
}

async function doLogin() {
  await loginFormRef.value?.validate()
  loading.value = true
  try {
    const resp = await login(loginForm.loginName, loginForm.password)
    if (resp.mustChangePassword) {
      // 强制改密：暂存会话（改密接口需登录态），改密成功后全清重新登录
      userStore.setLogin(resp)
      pwdForm.oldPassword = loginForm.password
      mustChange.value = true
      return
    }
    userStore.setLogin(resp)
    ElMessage.success(`欢迎，${resp.user.name}`)
    router.replace((route.query.redirect as string) || '/')
  } catch {
    // 错误提示由 request 拦截器统一处理
  } finally {
    loading.value = false
  }
}

async function doChangePassword() {
  await pwdFormRef.value?.validate()
  loading.value = true
  try {
    await changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    ElMessage.success('密码修改成功，请使用新密码登录')
    backToLogin()
  } catch {
    // 错误提示由 request 拦截器统一处理
  } finally {
    loading.value = false
  }
}

function backToLogin() {
  userStore.reset()
  mustChange.value = false
  loginForm.password = ''
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
}
</script>

<style scoped>
.login-page {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1a3a6b 0%, #2d5aa0 100%);
}

.login-card {
  width: 420px;
  padding: 24px 12px;
}

.login-title {
  color: #1a3a6b;
  margin: 0 0 8px;
  text-align: center;
}

.login-sub {
  color: #909399;
  margin: 0 0 32px;
  text-align: center;
}

.login-btn {
  width: 100%;
}

.cancel-btn {
  margin: 10px 0 0;
}

.change-tip {
  margin-bottom: 16px;
}
</style>
