<template>
  <div class="app-layout">
    <!-- 页面标题栏由宿主小程序原生导航栏承载（取 document.title），H5 内不再渲染，避免双标题 -->
    <main class="app-body" :class="{ 'with-tabbar': activeTab }"><slot /></main>
    <van-tabbar v-if="activeTab" :model-value="activeTab" fixed safe-area-inset-bottom @change="onTabChange">
      <van-tabbar-item name="report" icon="edit">提报</van-tabbar-item>
      <van-tabbar-item name="mine" icon="orders-o" :badge="needInfo || ''">我的需求</van-tabbar-item>
      <van-tabbar-item v-if="user.userInfo?.isAdmin" name="admin" icon="apps-o">需求整理</van-tabbar-item>
    </van-tabbar>
  </div>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { myNeedInfoCount } from '@/api/demand'
import { TOKEN_KEY } from '@/api/request'
const props = withDefaults(defineProps<{ activeTab?: '' | 'report' | 'mine' | 'admin' }>(), { activeTab: '' })
const router = useRouter()
const user = useUserStore()
// 待补充角标：NEED_INFO 需求数，与「待补充」tab 同口径；补充重提/撤销后自动消，不依赖通知已读
const needInfo = ref(0)
async function refreshNeedInfo() {
  if (!localStorage.getItem(TOKEN_KEY)) return
  try { needInfo.value = (await myNeedInfoCount()).count } catch { needInfo.value = 0 }
}
function onTabChange(name: string | number) { if (name !== props.activeTab) router.push(`/${name}`) }
onMounted(refreshNeedInfo)
</script>
<style scoped>
.app-layout { min-height: 100vh; background: #f5f6f8; }
.app-body { min-height: 100vh; }
/* 底部预留与 van-tabbar 实际高度一致（默认 50px + 安全区），避免内容与菜单栏之间留白 */
.with-tabbar { padding-bottom: calc(50px + env(safe-area-inset-bottom)); }
</style>
