<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="title">DemandHub 管理后台</h2>
      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="submit">
        <el-form-item prop="loginAccount">
          <el-input v-model="form.loginAccount" placeholder="登录账号 / 手机号" size="large" autofocus />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="form.password" type="password" placeholder="密码" size="large"
                    show-password @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" size="large" class="submit" :loading="loading" @click="submit">
          登 录
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/request'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ loginAccount: '', password: '' })
const rules: FormRules = {
  loginAccount: [{ required: true, message: '请输入登录账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submit() {
  await formRef.value?.validate().catch(() => Promise.reject())
  loading.value = true
  try {
    await auth.login(form.loginAccount.trim(), form.password)
    if (auth.mustChangePwd) {
      ElMessage.warning('首次登录请先修改密码')
      await router.push('/change-password')
    } else {
      await router.push((route.query.redirect as string) || '/')
    }
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; }
.login-card { width: 380px; }
.title { margin: 0 0 24px; text-align: center; font-size: 20px; color: #303133; }
.submit { width: 100%; }
</style>
