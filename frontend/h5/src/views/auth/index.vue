<template>
  <div class="auth-page">
    <!-- 错误态：票据校验失败（复用后端 AC07 文案） -->
    <div v-if="errorMsg" class="auth-result">
      <van-icon name="warning-o" size="56" color="#ee0a24" />
      <div class="result-title">登录失败</div>
      <div class="result-desc">{{ errorMsg }}</div>
      <van-button type="primary" block round class="result-btn" @click="goBack">返回创金零售</van-button>
    </div>

    <!-- 提示态：无 ticket 直接访问 -->
    <div v-else class="auth-result">
      <div class="auth-title">DemandHub</div>
      <div class="auth-sub">创金合信零售业务需求管理</div>
      <van-icon name="guide-o" size="56" color="#1F3A8A" class="hint-icon" />
      <div class="result-desc">{{ hintText }}</div>

      <!-- dev 专用：Mock 创金零售入口（模拟其首页签票后 302 跳入） -->
      <template v-if="isDev">
        <van-divider class="mock-divider">开发环境 Mock 入口</van-divider>
        <van-cell-group inset>
          <van-cell
            v-for="u in mockUsers"
            :key="u.channelUserId"
            :title="u.name"
            :label="u.orgName || '未分配组织'"
            is-link
            @click="enterAs(u)"
          />
        </van-cell-group>
        <van-loading v-if="loading" class="auth-loading" size="24px">签发票据中...</van-loading>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { mockIssueTicket, mockSsoEntry } from '@/api/auth'
import type { MockChannelUser } from '@/api/auth'

const route = useRoute()

/** 票据登录失败文案（后端 AC07 错误信息经 query.error 传入） */
const errorMsg = computed(() => (route.query.error as string) || '')

const isDev = import.meta.env.DEV
const isWecomUA = /MicroMessenger/i.test(navigator.userAgent)

/** 无 ticket 且非企微 UA：引导从创金零售进入；企微 UA 无 ticket：提示从首页进入 */
const hintText = computed(() =>
  isWecomUA
    ? '请从创金零售首页「需求提报」进入'
    : '请在企业微信中打开，并从创金零售首页「需求提报」进入'
)

const mockUsers = ref<MockChannelUser[]>([])
const loading = ref(false)

onMounted(async () => {
  if (!isDev || errorMsg.value) {
    return
  }
  try {
    mockUsers.value = await mockSsoEntry()
  } catch {
    // Mock 服务未开启（非 dev 配置）时仅展示提示页
  }
})

/** 模拟创金零售跳入：签一次性 ticket 后按对接标准 URL 跳转（走真实 ticket 链路） */
async function enterAs(u: MockChannelUser) {
  loading.value = true
  try {
    const { ticket } = await mockIssueTicket(u.channelUserId)
    window.location.assign(`/h5/report?from=chuangjinls&ticket=${ticket}`)
  } catch {
    loading.value = false
  }
}

function goBack() {
  if (window.history.length > 1) {
    window.history.back()
  } else {
    showToast('请从创金零售重新进入')
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  background: #f5f7fa;
  padding-top: 64px;
}

.auth-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0 32px;
}

.auth-title {
  font-size: 24px;
  font-weight: 600;
  color: #1F3A8A;
}

.auth-sub {
  font-size: 13px;
  color: #909399;
  margin-top: 6px;
}

.hint-icon {
  margin-top: 40px;
}

.result-title {
  font-size: 18px;
  font-weight: 600;
  color: #323233;
  margin-top: 16px;
}

.result-desc {
  font-size: 14px;
  color: #646566;
  text-align: center;
  line-height: 1.6;
  margin-top: 12px;
}

.result-btn {
  margin-top: 32px;
}

.mock-divider {
  margin-top: 40px;
}

.auth-loading {
  display: flex;
  justify-content: center;
  margin-top: 24px;
}
</style>
