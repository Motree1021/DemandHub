<template>
  <div class="app-layout">
    <van-nav-bar :title="title" :left-arrow="showBack" fixed placeholder class="app-navbar" @click-left="onBack">
      <template #right><slot name="right" /></template>
    </van-nav-bar>
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
const props = withDefaults(defineProps<{ title: string; showBack?: boolean; activeTab?: '' | 'report' | 'mine' | 'admin' }>(), { showBack: false, activeTab: '' })
const router = useRouter()
const user = useUserStore()
function onBack() { if (history.length > 1) router.back(); else router.replace('/mine') }
function onTabChange(name: string | number) { if (name !== props.activeTab) router.push(`/${name}`) }
</script>
<style scoped>
.app-layout { min-height: 100vh; background: #f5f6f8; }
.app-navbar { --van-nav-bar-background: linear-gradient(135deg, #1f3a8a, #2f56b8); --van-nav-bar-title-text-color: #fff; --van-nav-bar-text-color: #fff; --van-nav-bar-icon-color: #fff; }
.app-body { min-height: calc(100vh - 46px); }
.with-tabbar { padding-bottom: calc(66px + env(safe-area-inset-bottom)); }
</style>
