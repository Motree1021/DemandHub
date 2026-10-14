<template>
  <div class="pwd-page">
    <el-card class="pwd-card">
      <h2 class="title">修改密码</h2>
      <el-alert v-if="auth.mustChangePwd" type="warning" :closable="false"
                title="首次登录（或密码被重置）后必须先修改密码，才能继续使用系统" class="tip" />
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="原密码" prop="oldPassword">
          <el-input v-model="form.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="form.newPassword" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="form.confirm" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="submit">确认修改</el-button>
          <el-button @click="quit">退出登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/request'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const form = reactive({ oldPassword: '', newPassword: '', confirm: '' })
const rules: FormRules = {
  oldPassword: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 64, message: '新密码长度 8-64 位', trigger: 'blur' },
  ],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    { validator: (_r, v: string, cb) => v === form.newPassword ? cb() : cb(new Error('两次输入的密码不一致')), trigger: 'blur' },
  ],
}

async function submit() {
  await formRef.value?.validate().catch(() => Promise.reject())
  loading.value = true
  try {
    await auth.changePassword(form.oldPassword, form.newPassword)
    ElMessage.success('密码已修改，请重新登录')
    await auth.logout()
    await router.push('/login')
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '修改失败')
  } finally {
    loading.value = false
  }
}

async function quit() {
  await auth.logout()
  await router.push('/login')
}
</script>

<style scoped>
.pwd-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: #f0f2f5; }
.pwd-card { width: 460px; }
.title { margin: 0 0 16px; text-align: center; font-size: 20px; color: #303133; }
.tip { margin-bottom: 16px; }
</style>
