<template>
  <div class="auth-page">
    <h1>DemandHub</h1><p class="subtitle">创金合信零售业务需求提报</p>

    <!-- 白名单拦截（1123）：「暂未开放」友好落地页——柔和色调、不用告警红、无测试登录入口 -->
    <div v-if="isWhitelist" class="wl">
      <div class="wl-icon"><van-icon name="underway-o" size="38" color="#1f3a8a" /></div>
      <h2 class="wl-title">暂未开放</h2>
      <p class="wl-sub">当前仅白名单用户可以使用，<br>我们即将开放，敬请期待～</p>
      <div v-if="contact" class="contact-card">
        <div class="cc-title">如需开通访问权限</div>
        <div class="cc-body">{{ contact }}</div>
      </div>
      <van-button round block type="primary" class="wl-btn" @click="goBack">返回创金零售</van-button>
    </div>

    <!-- 其他状态：入口报错 / 未登录 / 登录过期（测试构建与本地开发保留手动登录入口） -->
    <template v-else>
      <van-icon :name="errorMsg ? 'warning-o' : 'guide-o'" size="56"
                :color="errorMsg ? '#ee0a24' : '#1f3a8a'" />
      <p>{{ errorMsg || (loginMode === 'none' ? '请从创金零售首页「需求提报」重新进入' : '请从创金零售进入，或使用下方测试账号登录') }}</p>
      <van-button round block type="primary" @click="goBack">返回创金零售</van-button>
      <div v-if="loginMode !== 'none'" class="dev-login">
        <van-divider>{{ loginMode === 'dev' ? '开发环境登录' : '测试环境登录' }}</van-divider>
        <van-field v-model="name" label="姓名" placeholder="用户表中登记的姓名" />
        <van-field v-model="userid" label="企业账号" placeholder="wecom_userid" />
        <van-button block :loading="loading" :disabled="!name.trim() || !userid.trim()" @click="login">{{ loginMode === 'dev' ? '开发登录' : '测试登录' }}</van-button>
      </div>
    </template>
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
// wl=1：白名单拦截（1123），展示「暂未开放」落地页；联系引导为公开接口（被拦用户无登录态），后台配了才显示
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
/* 白名单「暂未开放」落地页：单一品牌蓝软色调，不叠色、不告警 */
.wl { display: flex; flex-direction: column; align-items: center; }
.wl-icon { width: 84px; height: 84px; border-radius: 50%; background: #eef2fa; display: flex; align-items: center; justify-content: center; margin-bottom: 18px; }
.wl-title { font-size: 20px; color: #1f3a8a; margin: 0 0 10px; }
.wl-sub { font-size: 14px; color: #666; line-height: 1.9; margin: 0 0 26px; }
.wl-btn { max-width: 260px; }
.contact-card { background: #fff; border-radius: 12px; padding: 14px 18px; margin: 0 0 22px; text-align: left; border: 1px solid #eef0f4; width: 100%; box-sizing: border-box; }
.contact-card .cc-title { font-size: 12px; color: #969799; margin-bottom: 6px; }
.contact-card .cc-body { font-size: 14px; color: #323233; line-height: 1.6; }
</style>
