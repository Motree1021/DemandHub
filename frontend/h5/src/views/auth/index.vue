<template>
  <div class="auth-page">
    <div class="auth-header">
      <div class="auth-title">DemandHub</div>
      <div class="auth-sub">创金合信零售业务需求管理</div>
    </div>

    <van-cell-group inset title="选择登录身份（一期 Mock 企微静默授权）">
      <van-cell
        v-for="u in mockUsers"
        :key="u.userId"
        :title="u.name"
        :label="u.orgName"
        is-link
        @click="doLogin(u.mockCode)"
      />
    </van-cell-group>

    <van-loading v-if="loading" class="auth-loading" size="24px">登录中...</van-loading>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { listMockUsers, silentLogin } from '@/api/auth'
import type { MockUser } from '@/api/auth'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const mockUsers = ref<MockUser[]>([])
const loading = ref(false)

onMounted(async () => {
  mockUsers.value = await listMockUsers()
})

async function doLogin(code: string) {
  loading.value = true
  try {
    const resp = await silentLogin(code, userStore.from || undefined)
    userStore.setLogin(resp)
    showToast(`欢迎，${resp.user.name}`)
    const redirect = (route.query.redirect as string) || '/report'
    router.replace(redirect)
  } catch {
    // 提示由拦截器统一处理
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  background: #f5f7fa;
  padding-top: 48px;
}

.auth-header {
  text-align: center;
  margin-bottom: 32px;
}

.auth-title {
  font-size: 24px;
  font-weight: 600;
  color: #1a3a6b;
}

.auth-sub {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}

.auth-loading {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>
