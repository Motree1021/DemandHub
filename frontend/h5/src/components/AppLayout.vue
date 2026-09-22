<template>
  <div class="app-layout">
    <!-- 深蓝顶部导航（返回 + 标题），视觉对齐创金零售 -->
    <van-nav-bar
      :title="title"
      :left-arrow="showBack"
      fixed
      placeholder
      class="app-navbar"
      @click-left="onBack"
    >
      <template v-if="$slots.right" #right>
        <slot name="right" />
      </template>
    </van-nav-bar>

    <div class="app-body" :class="{ 'with-tabbar': showTabbar }">
      <slot />
    </div>

    <!-- 底部 TabBar：提报 / 我的 / 通知（未读角标）；嵌入态（from=chuangjinls）隐藏 -->
    <van-tabbar
      v-if="showTabbar"
      :model-value="activeTab"
      fixed
      safe-area-inset-bottom
      class="app-tabbar"
      @change="onTabChange"
    >
      <van-tabbar-item name="report" icon="edit">提报</van-tabbar-item>
      <van-tabbar-item name="mine" icon="orders-o">我的</van-tabbar-item>
      <van-tabbar-item name="notification" icon="bell" :badge="notifyStore.unread || ''">通知</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/store/notification'
import { useUserStore } from '@/store/user'

const props = withDefaults(
  defineProps<{
    title: string
    showBack?: boolean
    /** 当前高亮的 tab；传空串表示不显示 TabBar（子页面） */
    activeTab?: '' | 'report' | 'mine' | 'notification'
  }>(),
  { showBack: false, activeTab: '' }
)

const router = useRouter()
const notifyStore = useNotificationStore()
const userStore = useUserStore()

/** 嵌入态：从创金零售 App 跳入（from=chuangjinls）→ 隐藏 tabbar、仅留左上返回（任务 5.2） */
const isEmbed = computed(() => userStore.from === 'chuangjinls')
const showTabbar = computed(() => props.activeTab !== '' && !isEmbed.value)
const showBack = computed(() => props.showBack || isEmbed.value)

function onBack() {
  // 嵌入态入口页 history.back 即返回创金零售；独立访问无历史时回提报页
  if (window.history.length > 1) {
    router.back()
  } else {
    router.replace('/report')
  }
}

function onTabChange(name: string) {
  if (name !== props.activeTab) {
    router.replace(`/${name}`)
  }
}

onMounted(() => {
  // 进入主框架页面即启动未读角标轮询（store 内幂等）
  notifyStore.startPolling()
})
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: #f5f6f8;
}

/* 深蓝头部，对齐创金零售 #1F3A8A -> #2F56B8 渐变 */
.app-navbar {
  --van-nav-bar-background: linear-gradient(135deg, #1F3A8A 0%, #2F56B8 100%);
  --van-nav-bar-title-text-color: #fff;
  --van-nav-bar-text-color: #fff;
  --van-nav-bar-icon-color: #fff;
}

.app-body {
  min-height: calc(100vh - 46px);
}

.app-body.with-tabbar {
  /* 预留 TabBar 高度 + 底部安全区 */
  padding-bottom: calc(60px + env(safe-area-inset-bottom));
}

.app-tabbar {
  --van-tabbar-item-active-color: #1F3A8A;
  --van-tabbar-item-active-background: #fff;
}
</style>
