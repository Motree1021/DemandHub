<template>
  <div class="auth-page">
    <h1>DemandHub</h1><p class="subtitle">创金合信零售业务需求提报</p>
    <van-icon :name="isWhitelist ? 'lock' : (errorMsg ? 'warning-o' : 'guide-o')" size="56"
              :color="isWhitelist ? '#7a9cc6' : (errorMsg ? '#ee0a24' : '#1f3a8a')" />
    <p>{{ errorMsg || (loginMode === 'none' ? '请从创金零售首页「需求提报」重新进入' : '请从创金零售进入，或使用下方测试账号登录') }}</p>
    <p v-if="isWhitelist" class="wl-desc">当前账号未在访问白名单内，暂时无法使用科技需求收集服务</p>
    <div v-if="isWhitelist && contact" class="contact-card">
      <div class="cc-title">如需开通访问权限</div>
      <div class="cc-body">{{ contact }}</div>
    </div>
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
import { devLogin, testLogin, whitelistContact } from '@/api/auth'
import { useUserStore } from '@/store/user'
const route = useRoute(); const router = useRouter(); const user = useUserStore()
// test 优先便于测试环境构建脱离 dev 语义；生产构建两者皆无则不展示手动入口。
const loginMode: 'dev' | 'test' | 'none' = import.meta.env.VITE_TEST_LOGIN_ENTRY === 'true' ? 'test' : (import.meta.env.DEV ? 'dev' : 'none')
const errorMsg = computed(() => String(route.query.error || ''))
// wl=1：白名单拦截（1123），展示锁定图标与后台配置的联系引导（公开接口，被拦用户无登录态）
const isWhitelist = computed(() => route.query.wl === '1')
const contact = ref('')
if (isWhitelist.value) {
  whitelistContact().then(data => { contact.value = data.contact || '' }).catch(() => undefined)
}
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
.auth-page { max-width: var(--shell-width); margin: auto; padding: 64px 28px 24px; text-align: center; }.auth-page h1 { color: #1f3a8a; margin-bottom: 8px; }.subtitle { color: #777; font-size: 13px; margin-bottom: 36px; }.auth-page p { line-height: 1.8; color: #666; }.dev-login { margin-top: 40px; }.dev-login .van-button { margin-top: 16px; }
.wl-desc { font-size: 13px; color: #969799; margin-top: 4px; }
.contact-card { background: #fff; border-radius: 12px; padding: 14px 18px; margin: 22px 0; text-align: left; border: 1px solid #eef0f4; }
.contact-card .cc-title { font-size: 12px; color: #969799; margin-bottom: 6px; }
.contact-card .cc-body { font-size: 14px; color: #323233; line-height: 1.6; }
</style>
