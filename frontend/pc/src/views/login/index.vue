<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2 class="login-title">DemandHub 需求管理系统</h2>
      <p class="login-sub">创金合信基金零售业务线</p>

      <div v-if="loading" class="login-loading" v-loading="loading" element-loading-text="登录中..."></div>

      <template v-else>
        <!-- 一期：企微扫码以 Mock 用户选择代替；二期替换为真实企微二维码 -->
        <div class="mock-tip">
          <el-icon><Iphone /></el-icon>
          <span>请使用企业微信扫码登录（一期 Mock：选择用户模拟扫码）</span>
        </div>
        <el-select
          v-model="selectedCode"
          class="user-select"
          placeholder="选择登录用户（模拟企微身份）"
          size="large"
          filterable
        >
          <el-option
            v-for="u in mockUsers"
            :key="u.userId"
            :value="u.mockCode"
            :label="`${u.name}（${u.orgName}）`"
          />
        </el-select>
        <el-button
          type="primary"
          size="large"
          class="login-btn"
          :disabled="!selectedCode"
          @click="doLogin(selectedCode)"
        >
          企业微信登录
        </el-button>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/modules/user'
import { listMockUsers, loginByCode } from '@/api/auth'
import type { MockUser } from '@/api/auth'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const mockUsers = ref<MockUser[]>([])
const selectedCode = ref('')
const loading = ref(false)

onMounted(async () => {
  // 企微 OAuth 回调：URL 携带 code 时直接登录（一期 Mock / 二期真实回调共用）
  const code = route.query.code as string | undefined
  if (code) {
    await doLogin(code)
    return
  }
  mockUsers.value = await listMockUsers()
})

async function doLogin(code: string) {
  loading.value = true
  try {
    const resp = await loginByCode(code)
    userStore.setLogin(resp)
    ElMessage.success(`欢迎，${resp.user.name}`)
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  } catch {
    // 错误提示由 request 拦截器统一处理
  } finally {
    loading.value = false
  }
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

.mock-tip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #909399;
  font-size: 13px;
  margin-bottom: 16px;
}

.user-select {
  width: 100%;
  margin-bottom: 16px;
}

.login-btn {
  width: 100%;
}

.login-loading {
  height: 120px;
}
</style>
