<template>
  <el-container class="app-layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="app-aside">
      <div class="logo">
        <span v-if="!collapsed">DemandHub</span>
        <span v-else>DH</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        router
        background-color="#1a3a6b"
        text-color="#b8c7e0"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <template #title>工作台</template>
        </el-menu-item>
        <el-menu-item index="/demand/report">
          <el-icon><EditPen /></el-icon>
          <template #title>需求提报</template>
        </el-menu-item>
        <el-menu-item index="/demand/list">
          <el-icon><List /></el-icon>
          <template #title>需求列表</template>
        </el-menu-item>
        <el-menu-item index="/notification">
          <el-icon><Bell /></el-icon>
          <template #title>通知中心</template>
        </el-menu-item>
        <el-menu-item v-if="userStore.isAdmin" index="/system/grant">
          <el-icon><Setting /></el-icon>
          <template #title>角色授权管理</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <el-icon class="collapse-btn" @click="collapsed = !collapsed">
            <Fold v-if="!collapsed" />
            <Expand v-else />
          </el-icon>
          <span class="page-title">{{ route.meta.title || '工作台' }}</span>
        </div>
        <div class="header-right">
          <el-badge :value="unreadCount" :hidden="unreadCount === 0" class="notify-badge">
            <el-icon :size="18" @click="$router.push('/notification')"><Bell /></el-icon>
          </el-badge>
          <el-dropdown>
            <span class="user-info">
              <el-icon><Avatar /></el-icon>
              <span class="user-name">{{ userStore.name || '未登录' }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item>个人信息</el-dropdown-item>
                <el-dropdown-item divided @click="onLogout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/modules/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(false)
const unreadCount = ref(0) // 阶段 4 接入通知未读数接口

const activeMenu = computed(() => route.path)

async function onLogout() {
  await userStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-layout {
  height: 100vh;
}

.app-aside {
  background-color: #1a3a6b;
  transition: width 0.2s;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 1px;
}

.app-aside :deep(.el-menu) {
  border-right: none;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #ffffff;
  border-bottom: 1px solid #e4e7ed;
  padding: 0 16px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.collapse-btn {
  cursor: pointer;
  font-size: 18px;
}

.page-title {
  font-size: 16px;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.notify-badge {
  cursor: pointer;
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}

.app-main {
  background: #f5f7fa;
  padding: 16px;
}
</style>
