<template>
  <div class="dashboard">
    <!-- 快捷入口 -->
    <el-row :gutter="16" class="mb16">
      <el-col :span="6">
        <el-card shadow="hover" class="entry-card" @click="$router.push('/demand/report')">
          <el-icon :size="28" color="#1d4ed8"><EditPen /></el-icon>
          <div class="entry-title">提报需求</div>
          <div class="entry-desc">科技 / 物料 / 培训</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="entry-card" @click="$router.push('/demand/list')">
          <el-icon :size="28" color="#0d9488"><List /></el-icon>
          <div class="entry-title">需求列表</div>
          <div class="entry-desc">我的提报 / 本组织承接</div>
        </el-card>
      </el-col>
      <el-col :span="6" v-if="isManagerLike">
        <el-card shadow="hover" class="entry-card" @click="$router.push('/workbench/manager')">
          <el-icon :size="28" color="#d97706"><Files /></el-icon>
          <div class="entry-title">经理工作台</div>
          <div class="entry-desc">待受理 {{ queueCount }} 条</div>
        </el-card>
      </el-col>
      <el-col :span="6" v-if="isHandler">
        <el-card shadow="hover" class="entry-card" @click="$router.push('/workbench/handler')">
          <el-icon :size="28" color="#d97706"><Suitcase /></el-icon>
          <div class="entry-title">处理人工作台</div>
          <div class="entry-desc">领取 / 我的待办</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="entry-card" @click="$router.push('/notification')">
          <el-badge :value="notifyStore.unread" :hidden="notifyStore.unread === 0" :max="99">
            <el-icon :size="28" color="#dc2626"><Bell /></el-icon>
          </el-badge>
          <div class="entry-title">通知中心</div>
          <div class="entry-desc">未读 {{ notifyStore.unread }} 条</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 我的待办 / 最近动态 -->
    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="card-header">
              <span>{{ todoTitle }}</span>
              <el-link type="primary" @click="$router.push('/demand/list')">查看全部</el-link>
            </div>
          </template>
          <el-table :data="todoRows" v-loading="todoLoading" size="small">
            <el-table-column label="编号" width="160">
              <template #default="{ row }">
                <el-link type="primary" @click="$router.push(`/demand/detail/${row.id}`)">{{ row.demandNo }}</el-link>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column label="紧急" width="76">
              <template #default="{ row }">
                <el-tag :type="urgencyTagType(row.urgency)" size="small">{{ urgencyLabel(row.urgency) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="140">
              <template #default="{ row }">{{ fmtTime(row.submittedAt) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!todoRows.length && !todoLoading" description="暂无待办" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>最新通知</template>
          <el-empty v-if="!notices.length" description="暂无通知" :image-size="60" />
          <div v-for="n in notices" :key="n.id" class="notice-item" @click="$router.push('/notification')">
            <el-tag v-if="n.isRead === 0" type="danger" size="small" effect="dark" style="margin-right: 6px">新</el-tag>
            <span class="notice-title">{{ n.title }}</span>
            <div class="notice-time">{{ fmtTime(n.createdAt) }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { pageDemands, triageQueueCount, type DemandListItem } from '@/api/demand'
import { pageMyNotifications, type NotificationItem } from '@/api/notification'
import { useUserStore } from '@/store/modules/user'
import { useNotificationStore } from '@/store/modules/notification'
import { statusLabel, statusTagType, urgencyLabel, urgencyTagType, fmtTime } from '@/utils/format'

const userStore = useUserStore()
const notifyStore = useNotificationStore()

const todoRows = ref<DemandListItem[]>([])
const todoLoading = ref(false)
const notices = ref<NotificationItem[]>([])
const queueCount = ref(0)

const isManagerLike = computed(
  () => userStore.roles.includes('MANAGER') || userStore.roles.includes('EXECUTIVE') || userStore.isAdmin
)
const isHandler = computed(() => userStore.roles.includes('HANDLER'))

// 角色族版不设提报人角色：非经理/非处理人的普通用户视角即"我的在途提报"
const todoTitle = computed(() => (!isManagerLike.value ? '我的在途提报' : '我的待办'))

async function loadTodo() {
  todoLoading.value = true
  try {
    // 普通用户视角：我的在途提报；经理/处理人视角：本组织在途（数据权限自动过滤）
    const mine = !isManagerLike.value && !isHandler.value
    const data = await pageDemands({ current: 1, size: 5, mine })
    // 在途 = 非终态
    todoRows.value = data.records.filter((d) => !['DONE', 'CLOSED'].includes(d.status)).slice(0, 5)
  } finally {
    todoLoading.value = false
  }
}

onMounted(async () => {
  loadTodo()
  pageMyNotifications({ current: 1, size: 5 }).then((d) => (notices.value = d.records))
  if (isManagerLike.value) {
    triageQueueCount().then((c) => (queueCount.value = c)).catch(() => (queueCount.value = 0))
  }
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.entry-card {
  text-align: center;
  cursor: pointer;
  transition: transform 0.15s;
}

.entry-card:hover {
  transform: translateY(-2px);
}

.entry-title {
  font-weight: 600;
  margin-top: 8px;
}

.entry-desc {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 4px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.notice-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  font-size: 13px;
}

.notice-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notice-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 2px;
}
</style>
