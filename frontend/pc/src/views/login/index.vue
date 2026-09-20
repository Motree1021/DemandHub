<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="login-title">DemandHub 需求管理系统</h2>
      <p class="login-sub">创金合信基金零售业务线</p>
      <el-button type="primary" size="large" class="login-btn" @click="mockLogin">
        企业微信登录（阶段 2 接入）
      </el-button>
      <el-button size="large" class="login-btn" @click="enterAnyway">先进入看看</el-button>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/modules/user'
import { ElMessage } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()

function mockLogin() {
  ElMessage.info('企微 OAuth 将在阶段 2 接入')
}

function enterAnyway() {
  userStore.setToken('dev-placeholder-token')
  userStore.name = '开发占位用户'
  router.push('/')
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
  width: 400px;
  text-align: center;
  padding: 24px 12px;
}

.login-title {
  color: #1a3a6b;
  margin: 0 0 8px;
}

.login-sub {
  color: #909399;
  margin: 0 0 32px;
}

.login-btn {
  width: 100%;
  margin: 8px 0 0;
}
</style>
