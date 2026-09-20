<template>
  <div class="h5-page">
    <van-nav-bar title="我的需求" />
    <div class="content">
      <van-empty description="我的需求列表将在阶段 6 开发" />
    </div>
    <van-tabbar v-model="active" route>
      <van-tabbar-item icon="edit" to="/report">提报</van-tabbar-item>
      <van-tabbar-item icon="orders-o" to="/mine">我的</van-tabbar-item>
      <van-tabbar-item icon="bell" to="/notification">通知</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const active = ref(1)
</script>

<style scoped>
.h5-page {
  min-height: 100vh;
  background: #f5f7fa;
}

.content {
  padding-bottom: 60px;
}
</style>
