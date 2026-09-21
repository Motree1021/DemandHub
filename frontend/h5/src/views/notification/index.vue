<template>
  <app-layout title="通知" active-tab="notification">
    <template #right>
      <span v-if="rows.some((n) => n.isRead === 0)" class="read-all" @click="onMarkAllRead">全部已读</span>
    </template>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        finished-text="没有更多了"
        :immediate-check="false"
        @load="onLoad"
      >
        <div
          v-for="n in rows"
          :key="n.id"
          class="notify-item"
          :class="{ unread: n.isRead === 0 }"
          @click="onOpen(n)"
        >
          <div class="notify-dot" v-if="n.isRead === 0"></div>
          <div class="notify-main">
            <div class="notify-title">{{ n.title }}</div>
            <div class="notify-content">{{ n.content }}</div>
            <div class="notify-time">{{ fmtTime(n.createdAt) }}</div>
          </div>
          <van-icon name="arrow" class="notify-arrow" />
        </div>
        <van-empty v-if="finished && !rows.length" description="暂无通知" />
      </van-list>
    </van-pull-refresh>
  </app-layout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import { pageMyNotifications, markRead, markAllRead, type NotificationItem } from '@/api/notification'
import { useNotificationStore } from '@/store/notification'
import { fmtTime } from '@/utils/format'

const router = useRouter()
const notifyStore = useNotificationStore()

const PAGE_SIZE = 15

const rows = ref<NotificationItem[]>([])
const current = ref(1)
const loading = ref(false)
const refreshing = ref(false)
const finished = ref(false)

async function fetchPage(): Promise<void> {
  const data = await pageMyNotifications({ current: current.value, size: PAGE_SIZE })
  rows.value.push(...data.records)
  current.value += 1
  finished.value = rows.value.length >= data.total
}

async function onLoad() {
  try {
    await fetchPage()
  } finally {
    loading.value = false
  }
}

async function onRefresh() {
  refreshing.value = true
  try {
    current.value = 1
    rows.value = []
    finished.value = false
    await fetchPage()
    notifyStore.refresh()
  } finally {
    refreshing.value = false
  }
}

/** 点击通知：未读先标记已读，有关联需求则跳详情 */
async function onOpen(n: NotificationItem) {
  if (n.isRead === 0) {
    await markRead(n.id)
    n.isRead = 1
    notifyStore.refresh()
  }
  if (n.demandId) {
    router.push(`/demand/${n.demandId}`)
  }
}

async function onMarkAllRead() {
  await markAllRead()
  rows.value.forEach((n) => (n.isRead = 1))
  notifyStore.refresh()
  showSuccessToast('已全部标记为已读')
}

onMounted(onRefresh)
</script>

<style scoped>
.read-all {
  font-size: 13px;
  color: #fff;
}

.notify-item {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fff;
  border-radius: 12px;
  margin: 10px 12px;
  padding: 14px 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

/* 未读高亮 / 已读置灰 */
.notify-item.unread .notify-title {
  color: #1a1a1a;
  font-weight: 600;
}

.notify-item:not(.unread) {
  opacity: 0.62;
}

.notify-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ff4757;
  flex-shrink: 0;
}

.notify-main {
  flex: 1;
  min-width: 0;
}

.notify-title {
  font-size: 14px;
  color: #555;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notify-content {
  font-size: 12px;
  color: #888;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.notify-time {
  font-size: 11px;
  color: #aaa;
  margin-top: 6px;
}

.notify-arrow {
  color: #ccc;
  flex-shrink: 0;
}
</style>
