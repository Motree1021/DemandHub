<template>
  <div class="notify-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <el-radio-group v-model="filter" @change="load(1)">
            <el-radio-button :value="undefined">全部</el-radio-button>
            <el-radio-button :value="false">未读</el-radio-button>
            <el-radio-button :value="true">已读</el-radio-button>
          </el-radio-group>
          <div>
            <el-button text type="primary" @click="prefDrawer = true">通知偏好设置</el-button>
            <el-button type="primary" plain :disabled="notifyStore.unread === 0" @click="onReadAll">全部已读</el-button>
          </div>
        </div>
      </template>

      <el-empty v-if="!rows.length && !loading" description="暂无通知" />
      <div v-loading="loading">
        <div
          v-for="n in rows"
          :key="n.id"
          class="notify-item"
          :class="{ unread: n.isRead === 0 }"
          @click="onOpen(n)"
        >
          <div class="notify-dot" />
          <div class="notify-body">
            <div class="notify-title">
              {{ n.title }}
              <el-tag v-if="n.channel === 'WECOM'" size="small" effect="plain" style="margin-left: 6px">企微</el-tag>
            </div>
            <div class="notify-content">{{ n.content }}</div>
            <div class="notify-time">{{ fmtTime(n.createdAt, true) }}</div>
          </div>
          <el-button v-if="n.isRead === 0" size="small" text type="primary" @click.stop="onRead(n)">标记已读</el-button>
        </div>
      </div>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="query.size"
        :current-page="query.current"
        @current-change="load"
      />
    </el-card>

    <!-- 偏好设置抽屉 -->
    <el-drawer v-model="prefDrawer" title="通知偏好设置" size="380px">
      <el-alert type="info" :closable="false" title="关闭后对应类型的站内信与企微推送都不再发送；待办提醒为关键通知不可关闭" style="margin-bottom: 14px" />
      <div v-for="p in prefs" :key="p.notifyType" class="pref-item">
        <div>
          <div>{{ prefLabel(p.notifyType) }}</div>
          <div class="muted">{{ prefDesc(p.notifyType) }}</div>
        </div>
        <el-switch
          :model-value="p.enabled"
          :disabled="!p.closable"
          @change="(v: boolean) => onTogglePref(p, v)"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  pageMyNotifications,
  markRead,
  markAllRead,
  listPreferences,
  updatePreference,
  type NotificationItem,
  type PreferenceItem
} from '@/api/notification'
import { useNotificationStore } from '@/store/modules/notification'
import { fmtTime } from '@/utils/format'

const router = useRouter()
const notifyStore = useNotificationStore()

const rows = ref<NotificationItem[]>([])
const total = ref(0)
const loading = ref(false)
const filter = ref<boolean | undefined>(false)
const prefDrawer = ref(false)
const prefs = ref<PreferenceItem[]>([])

const query = reactive({ current: 1, size: 10 })

async function load(page = query.current) {
  query.current = page
  loading.value = true
  try {
    const data = await pageMyNotifications({ current: query.current, size: query.size, isRead: filter.value })
    rows.value = data.records
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function onRead(n: NotificationItem) {
  await markRead(n.id)
  n.isRead = 1
  notifyStore.refresh()
}

async function onReadAll() {
  const res = await markAllRead()
  ElMessage.success(`已将 ${res.updated} 条通知标记为已读`)
  notifyStore.refresh()
  load(1)
}

async function onOpen(n: NotificationItem) {
  if (n.isRead === 0) {
    onRead(n)
  }
  // 优先按 link 跳，其次按 demandId 跳详情
  if (n.link) {
    router.push(n.link)
  } else if (n.demandId) {
    router.push(`/demand/detail/${n.demandId}`)
  }
}

const PREF_META: Record<string, { label: string; desc: string }> = {
  TODO: { label: '待办提醒', desc: '分派、领取等待办事项（不可关闭）' },
  STATUS_CHANGE: { label: '状态变更', desc: '需求受理、退回、关闭、开始处理等' },
  MENTION: { label: '@ 提醒', desc: '评论中 @ 你时提醒' },
  ASSIGN: { label: '任务分派', desc: '有新任务分派给你时提醒' },
  REVIEW_REQUEST: { label: '评审请求', desc: '方案提交评审时提醒' },
  ACCEPTANCE_REQUEST: { label: '验收请求', desc: '需求提交验收时提醒' },
  SLA_ALERT: { label: 'SLA 超时告警', desc: '需求停留超时预警/告警' }
}

function prefLabel(t: string): string {
  return PREF_META[t]?.label || t
}

function prefDesc(t: string): string {
  return PREF_META[t]?.desc || ''
}

async function onTogglePref(p: PreferenceItem, v: boolean) {
  await updatePreference(p.notifyType, v)
  p.enabled = v
  ElMessage.success('偏好已更新')
}

onMounted(async () => {
  load(1)
  prefs.value = await listPreferences()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.notify-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
}

.notify-item:hover {
  background: var(--el-fill-color-light);
}

.notify-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 8px;
  background: transparent;
  flex-shrink: 0;
}

.notify-item.unread .notify-dot {
  background: var(--el-color-danger);
}

.notify-item.unread .notify-title {
  font-weight: 600;
}

.notify-body {
  flex: 1;
  min-width: 0;
}

.notify-title {
  font-size: 14px;
}

.notify-content {
  color: var(--el-text-color-regular);
  font-size: 13px;
  margin-top: 4px;
  white-space: pre-wrap;
}

.notify-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
}

.pager {
  margin-top: 14px;
  justify-content: flex-end;
}

.pref-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
