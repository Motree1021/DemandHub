<template>
  <div>
    <div class="toolbar">
      <el-radio-group v-model="filter" @change="load(1)">
        <el-radio-button :value="false">全部</el-radio-button>
        <el-radio-button :value="true">仅未读</el-radio-button>
      </el-radio-group>
      <div class="actions">
        <el-button @click="prefVisible = true">偏好设置</el-button>
        <el-button type="primary" plain :disabled="!unread" @click="onReadAll">
          全部已读{{ unread ? `（${unread}）` : '' }}
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading" @row-click="onOpen" row-class-name="mail-row">
        <el-table-column label="" width="36">
          <template #default="{ row }">
            <el-badge v-if="!row.isRead" is-dot />
          </template>
        </el-table-column>
        <el-table-column label="标题" min-width="220">
          <template #default="{ row }">
            <span :class="{ unread: !row.isRead }">{{ row.title }}</span>
            <el-tag v-if="row.notifyType" size="small" class="type-tag" :type="tagType(row.notifyType)">
              {{ typeLabel(row.notifyType) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="content" label="内容" min-width="320" show-overflow-tooltip />
        <el-table-column prop="createdAt" label="时间" width="170" />
      </el-table>
      <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                     :page-size="size" :current-page="current" @current-change="load" />
    </el-card>

    <el-drawer v-model="prefVisible" title="通知偏好" size="360px">
      <p class="pref-tip">关闭后对应类型的通知将不再投递到你的信箱；「待办提醒」不可关闭。</p>
      <div v-for="item in preferences" :key="item.notifyType" class="pref-row">
        <span>{{ typeLabel(item.notifyType) }}</span>
        <el-switch :model-value="item.enabled" :disabled="!item.closable"
                   @change="(value: boolean) => onToggle(item, value)" />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { notificationApi } from '@/api'
import type { NotificationRow, PreferenceRow } from '@/api'

const NOTIFY_TYPE_LABELS: Record<string, string> = {
  TODO: '待办提醒',
  STATUS_CHANGE: '状态变更',
  ASSIGN: '分派通知',
  REVIEW_REQUEST: '评审请求',
  ACCEPTANCE_REQUEST: '验收请求',
  SLA_ALERT: 'SLA 预警',
  MENTION: '提及',
}
const typeLabel = (type: string) => NOTIFY_TYPE_LABELS[type] || type
const tagType = (type: string) =>
  (type === 'SLA_ALERT' ? 'danger' : type === 'TODO' ? 'warning' : 'info') as 'danger' | 'warning' | 'info'

const router = useRouter()
const rows = ref<NotificationRow[]>([])
const total = ref(0)
const current = ref(1)
const size = 10
const filter = ref(false)
const loading = ref(false)
const unread = ref(0)
const prefVisible = ref(false)
const preferences = ref<PreferenceRow[]>([])

async function load(page = current.value) {
  loading.value = true
  try {
    const data = await notificationApi.mine({ current: page, size, isRead: filter.value ? false : undefined })
    rows.value = data.records
    total.value = data.total
    current.value = page
    unread.value = (await notificationApi.unreadCount()).count
  } finally {
    loading.value = false
  }
}

async function onOpen(row: NotificationRow) {
  if (!row.isRead) {
    await notificationApi.read(row.id)
    row.isRead = true
    unread.value = Math.max(0, unread.value - 1)
  }
  if (row.link) router.push(row.link)
}

async function onReadAll() {
  await notificationApi.readAll()
  ElMessage.success('已全部标记为已读')
  await load(1)
}

async function onToggle(item: PreferenceRow, value: boolean) {
  await notificationApi.savePreference(item.notifyType, value)
  item.enabled = value
  ElMessage.success('偏好已保存')
}

onMounted(async () => {
  await load(1)
  preferences.value = await notificationApi.preferences()
})
</script>

<style scoped>
.toolbar { display: flex; justify-content: space-between; margin-bottom: 12px; }
.unread { font-weight: 600; }
.type-tag { margin-left: 8px; }
.pager { margin-top: 12px; justify-content: flex-end; }
.pref-tip { color: #909399; font-size: 13px; margin-top: 0; }
.pref-row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #f0f0f0; }
:global(.mail-row) { cursor: pointer; }
</style>
