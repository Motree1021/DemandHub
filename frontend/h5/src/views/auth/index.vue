<template>
  <div class="auth-page">
    <h1>DemandHub</h1><p class="subtitle">创金合信零售业务需求提报</p>
    <van-icon :name="errorMsg ? 'warning-o' : 'guide-o'" size="56" :color="errorMsg ? '#ee0a24' : '#1f3a8a'" />
    <p>{{ errorMsg || (loginMode === 'none' ? '请从创金零售首页「需求提报」重新进入' : '请从创金零售进入，或使用下方测试账号登录') }}</p>
    <van-button round block type="primary" @click="goBack">返回创金零售</van-button>
    <div v-if="loginMode !== 'none'" class="dev-login">
      <van-divider>{{ loginMode === 'dev' ? '开发环境登录' : '测试环境登录' }}</van-divider>
      <van-field v-model="name" label="姓名" placeholder="用户表中登记的姓名" />
      <van-field v-model="userid" label="企业账号" placeholder="wecom_userid" />
      <van-button block :loading="loading" :disabled="!name.trim() || !userid.trim()" @click="login">{{ loginMode === 'dev' ? '开发登录' : '测试登录' }}</van-button>
    </div>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { devLogin, testLogin } from '@/api/auth'
import { useUserStore } from '@/store/user'
const route = useRoute(); const router = useRouter(); const user = useUserStore()
// test 优先便于测试环境构建脱离 dev 语义；生产构建两者皆无则不展示手动入口。
const loginMode: 'dev' | 'test' | 'none' = import.meta.env.VITE_TEST_LOGIN_ENTRY === 'true' ? 'test' : (import.meta.env.DEV ? 'dev' : 'none')
const errorMsg = computed(() => String(route.query.error || ''))
const name = ref(''); const userid = ref(''); const loading = ref(false)
async function login() {
  loading.value = true
  try {
    user.setLogin(await (loginMode === 'dev' ? devLogin : testLogin)(name.value.trim(), userid.value.trim()))
    const redirect = String(route.query.redirect || '/report')
    await router.replace(redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/report')
  } catch { /* API 已展示错误 */ } finally { loading.value = false }
}
function goBack() { if (history.length > 1) history.back(); else showToast('请关闭此页面，从创金零售重新进入') }
</script>
<style scoped>
.auth-page { max-width: 480px; margin: auto; padding: 64px 28px 24px; text-align: center; }.auth-page h1 { color: #1f3a8a; margin-bottom: 8px; }.subtitle { color: #777; font-size: 13px; margin-bottom: 36px; }.auth-page p { line-height: 1.8; color: #666; }.dev-login { margin-top: 40px; }.dev-login .van-button { margin-top: 16px; }
</style>
