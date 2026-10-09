<template>
  <div class="app-layout">
    <!-- 页面标题栏由宿主小程序原生导航栏承载（取 document.title），H5 内不再渲染，避免双标题 -->
    <main class="app-body" :class="{ 'with-tabbar': activeTab }"><slot /></main>
    <van-tabbar v-if="activeTab" :model-value="activeTab" fixed safe-area-inset-bottom @change="onTabChange">
      <van-tabbar-item name="report" icon="edit">提报</van-tabbar-item>
      <van-tabbar-item name="mine" icon="orders-o">我的需求</van-tabbar-item>
      <van-tabbar-item v-if="user.userInfo?.isAdmin" name="admin" icon="apps-o">需求整理</van-tabbar-item>
    </van-tabbar>
  </div>
</template>
<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
const props = withDefaults(defineProps<{ activeTab?: '' | 'report' | 'mine' | 'admin' }>(), { activeTab: '' })
const router = useRouter()
const user = useUserStore()
function onTabChange(name: string | number) { if (name !== props.activeTab) router.push(`/${name}`) }
</script>
<style scoped>
.app-layout { min-height: 100vh; background: #f5f6f8; }
.app-body { min-height: 100vh; }
/* 底部预留与 van-tabbar 实际高度一致（默认 50px + 安全区），避免内容与菜单栏之间留白 */
.with-tabbar { padding-bottom: calc(50px + env(safe-area-inset-bottom)); }
</style>
