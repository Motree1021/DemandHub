<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">DemandHub 管理后台</div>
      <el-menu :default-active="$route.path" :default-openeds="defaultOpeneds" router background-color="#001529" text-color="#a6adb4"
               active-text-color="#ffffff">
        <!-- 工作台 -->
        <el-sub-menu index="group-workspace">
          <template #title>
            <el-icon><Monitor /></el-icon>
            <span>工作台</span>
          </template>
          <el-menu-item index="/my-tasks">
            <el-icon><List /></el-icon>
            <span>我的处理</span>
          </el-menu-item>
          <el-menu-item v-if="canTriage" index="/triage">
            <el-icon><Stamp /></el-icon>
            <span>受理分派</span>
          </el-menu-item>
          <el-menu-item index="/demands">
            <el-icon><Files /></el-icon>
            <span>需求列表</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 数据洞察 -->
        <el-sub-menu v-if="canBoard" index="group-board">
          <template #title>
            <el-icon><TrendCharts /></el-icon>
            <span>数据洞察</span>
          </template>
          <el-menu-item index="/board/manager">
            <el-icon><DataAnalysis /></el-icon>
            <span>经营看板</span>
          </el-menu-item>
          <el-menu-item index="/board/org">
            <el-icon><OfficeBuilding /></el-icon>
            <span>组织看板</span>
          </el-menu-item>
          <el-menu-item index="/report">
            <el-icon><Download /></el-icon>
            <span>报表导出</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 需求配置 -->
        <el-sub-menu v-if="isAdmin" index="group-demand-conf">
          <template #title>
            <el-icon><Tools /></el-icon>
            <span>需求配置</span>
          </template>
          <el-menu-item index="/demand-types">
            <el-icon><Files /></el-icon>
            <span>类型管理</span>
          </el-menu-item>
          <el-menu-item index="/state-machines">
            <el-icon><Connection /></el-icon>
            <span>状态机管理</span>
          </el-menu-item>
          <el-menu-item index="/sla-configs">
            <el-icon><AlarmClock /></el-icon>
            <span>SLA 配置</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 组织权限（含渠道接入配置与渠道身份治理） -->
        <el-sub-menu v-if="isAdmin" index="group-org">
          <template #title>
            <el-icon><Avatar /></el-icon>
            <span>组织权限</span>
          </template>
          <el-menu-item index="/users">
            <el-icon><User /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item index="/channel-identities">
            <el-icon><Key /></el-icon>
            <span>渠道身份</span>
          </el-menu-item>
          <el-menu-item index="/orgs">
            <el-icon><OfficeBuilding /></el-icon>
            <span>组织管理</span>
          </el-menu-item>
          <el-menu-item index="/channels">
            <el-icon><Share /></el-icon>
            <span>渠道管理</span>
          </el-menu-item>
          <el-menu-item index="/channel-whitelist">
            <el-icon><Lock /></el-icon>
            <span>渠道白名单</span>
          </el-menu-item>
        </el-sub-menu>

        <!-- 系统设置 -->
        <el-sub-menu v-if="isAdmin" index="group-sys">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统设置</span>
          </template>
          <el-menu-item index="/notify-templates">
            <el-icon><BellFilled /></el-icon>
            <span>通知模板</span>
          </el-menu-item>
          <el-menu-item index="/sys-dicts">
            <el-icon><Collection /></el-icon>
            <span>字典管理</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="breadcrumb">{{ $route.meta.title || '我的处理' }}</span>
        <div class="header-right">
          <el-badge :value="unread" :hidden="!unread" :max="99" class="bell">
            <el-icon :size="20" @click="router.push('/notifications')"><Bell /></el-icon>
          </el-badge>
          <el-dropdown @command="onCommand">
            <span class="user-area">
              <el-avatar :size="28" class="avatar">{{ auth.user?.name?.slice(0, 1) }}</el-avatar>
              <span class="name">{{ auth.user?.name }}</span>
              <el-tag size="small" :type="roleTagType">{{ roleLabel }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="pwd">修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AlarmClock, Avatar, Bell, BellFilled, Collection, Connection, DataAnalysis, Download, Files, Key, List, Lock, Monitor, OfficeBuilding, Setting, SetUp, Share, Stamp, Tools, TrendCharts, User,
} from '@element-plus/icons-vue'
import { notificationApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const ROLE_LABELS: Record<string, string> = {
  ADMIN: '管理员', EXECUTIVE: '管理者', MANAGER: '经理', HANDLER: '处理人', REPORTER: '提报人',
}
const ROLE_TAG_TYPES = { ADMIN: 'danger', EXECUTIVE: 'warning', MANAGER: 'primary', HANDLER: 'info', REPORTER: 'info' } as const

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const unread = ref(0)

const roleLabel = computed(() => ROLE_LABELS[auth.role || ''] || auth.role || '')
const roleTagType = computed(() => ROLE_TAG_TYPES[(auth.role || 'HANDLER') as keyof typeof ROLE_TAG_TYPES])
// P4 角色放开：受理分派=经理族（ADMIN/MANAGER/EXECUTIVE）；看板与报表=经理/管理者（ADMIN 直通）
// 多角色：任一有效角色命中即可（auth.roles=主角色 ∪ 兼任授权）
const isAdmin = computed(() => auth.roles.includes('ADMIN'))
const canTriage = computed(() => auth.roles.some(r => ['ADMIN', 'MANAGER', 'EXECUTIVE'].includes(r)))
const canBoard = computed(() => auth.roles.some(r => ['ADMIN', 'MANAGER', 'EXECUTIVE'].includes(r)))

// 默认展开当前路由所在分组；其余收起，可手动多组同时展开
const defaultOpeneds = computed(() => {
  const p = route.path
  if (['/my-tasks', '/triage', '/demands'].some(x => p.startsWith(x))) return ['group-workspace']
  if (['/board', '/report'].some(x => p.startsWith(x))) return ['group-board']
  if (['/demand-types', '/state-machines', '/sla-configs'].some(x => p.startsWith(x))) return ['group-demand-conf']
  if (['/users', '/orgs', '/channels', '/channel-whitelist', '/channel-identities'].some(x => p.startsWith(x))) return ['group-org']
  if (['/notify-templates', '/sys-dicts'].some(x => p.startsWith(x))) return ['group-sys']
  return []
})

async function refreshUnread() {
  unread.value = await notificationApi.unreadCount().then(data => data.count).catch(() => 0)
}

async function onCommand(cmd: string) {
  if (cmd === 'pwd') return router.push('/change-password')
  if (cmd === 'logout') {
    await auth.logout()
    await router.push('/login')
  }
}

// access/refresh 双票都失效时（如他端改密被踢下线），跳回登录页
const onExpired = () => { auth.user = null; router.push('/login') }
let timer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  window.addEventListener('demandhub-admin:unauthorized', onExpired)
  refreshUnread()
  timer = setInterval(refreshUnread, 30000)  // 未读角标 30s 轮询
})
onUnmounted(() => {
  window.removeEventListener('demandhub-admin:unauthorized', onExpired)
  clearInterval(timer)
})
</script>

<style scoped>
.layout { min-height: 100vh; }
.aside { background: #001529; }
.logo { height: 60px; line-height: 60px; text-align: center; color: #fff; font-size: 15px; font-weight: 600; letter-spacing: 1px; }
.header { display: flex; align-items: center; justify-content: space-between; background: #fff; border-bottom: 1px solid #e4e7ed; }
.header-right { display: flex; align-items: center; gap: 20px; }
.bell { cursor: pointer; line-height: 1; }
.user-area { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.avatar { background: #409eff; color: #fff; font-size: 13px; }
.name { font-size: 14px; color: #303133; }
.main { background: #f0f2f5; }
/* 深色侧边栏下的分组菜单适配 */
.aside :deep(.el-menu) { border-right: none; }
.aside :deep(.el-menu--inline) { background-color: #000c17; }
.aside :deep(.el-menu--inline .el-menu-item) { background-color: transparent; }
.aside :deep(.el-menu--inline .el-menu-item:hover) { background-color: #001f3f; }
.aside :deep(.el-sub-menu__title:hover) { background-color: #001f3f; }
</style>
