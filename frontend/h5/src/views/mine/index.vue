<template>
  <app-layout title="我的需求" active-tab="mine">
    <template #right>
      <span v-if="isManager" class="triage-entry" @click="router.push('/triage')">待受理队列</span>
    </template>

    <van-search v-model="keyword" placeholder="搜索标题 / 需求编号" @search="onRefresh" @clear="onRefresh" />

    <van-tabs v-model:active="tab" sticky offset-top="46" @change="onRefresh">
      <van-tab title="我提的" name="mine" />
      <van-tab title="我待办的" name="todo" />
    </van-tabs>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        finished-text="没有更多了"
        :immediate-check="false"
        @load="onLoad"
      >
        <div v-for="d in rows" :key="d.id" class="demand-item" @click="router.push(`/demand/${d.id}`)">
          <div class="demand-top">
            <span class="demand-no">{{ d.demandNo }}</span>
            <span class="tag" :style="tagStyle(statusMeta(d.status))">{{ statusLabel(d.status) }}</span>
          </div>
          <div class="demand-title">
            <span class="tag type-tag" :style="tagStyle(typeMeta(d.demandTypeCode))">{{ typeShortLabel(d.demandTypeCode, d.typeName) }}</span>
            <span class="title-text">{{ d.title }}</span>
            <span v-if="d.onHold === 1" class="tag hold-tag">挂起</span>
          </div>
          <div class="demand-meta">
            <span class="meta-left">{{ metaText(d) }}</span>
            <span class="meta-right" :style="{ color: urgencyMeta(d.urgency).color }">{{ urgencyLabel(d.urgency) }}</span>
          </div>
        </div>
        <van-empty v-if="finished && !rows.length" :description="tab === 'mine' ? '还没有提报过需求' : '暂无待办事项'" />
      </van-list>
    </van-pull-refresh>
  </app-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'
import { pageDemands, type DemandListItem } from '@/api/demand'
import { useUserStore } from '@/store/user'
import { statusLabel, statusMeta, typeMeta, typeShortLabel, urgencyLabel, urgencyMeta, fmtTime, type ColorMeta } from '@/utils/format'

const router = useRouter()
const userStore = useUserStore()

const PAGE_SIZE = 10

const tab = ref<'mine' | 'todo'>('mine')
const keyword = ref('')
const rows = ref<DemandListItem[]>([])
const current = ref(1)
const loading = ref(false)
const refreshing = ref(false)
const finished = ref(false)

const isManager = computed(() => userStore.userInfo?.roles?.includes('DEMAND_MANAGER'))

function tagStyle(m: ColorMeta) {
  return { background: m.bg, color: m.color }
}

function metaText(d: DemandListItem): string {
  if (tab.value === 'mine') {
    const org = d.assigneeOrgName ? `承接：${d.assigneeOrgName}` : '待承接'
    return `${org} · ${fmtTime(d.submittedAt || d.createdAt)} 提交`
  }
  return `提报：${d.submitterName || '-'} · ${fmtTime(d.submittedAt || d.createdAt)}`
}

/** 我提的：服务端分页（mine=true） */
async function fetchMine(): Promise<{ list: DemandListItem[]; total: number }> {
  const data = await pageDemands({
    current: current.value,
    size: PAGE_SIZE,
    keyword: keyword.value || undefined,
    mine: true,
    submittedOrder: 'desc'
  })
  return { list: data.records, total: data.total }
}

/**
 * 我待办的：需我动作的需求（退回补充 NEED_INFO + 待验收 ACCEPTANCE）。
 * 后端 status 仅支持单值，按 PC 端先例并发查询后合并（个人待办数据量小）。
 */
async function fetchTodo(): Promise<{ list: DemandListItem[]; total: number }> {
  const base = { current: 1, size: 50, mine: true, keyword: keyword.value || undefined, submittedOrder: 'desc' as const }
  const [needInfo, acceptance] = await Promise.all([
    pageDemands({ ...base, status: 'NEED_INFO' }),
    pageDemands({ ...base, status: 'ACCEPTANCE' })
  ])
  const merged = [...needInfo.records, ...acceptance.records].sort((a, b) =>
    (b.submittedAt || b.createdAt).localeCompare(a.submittedAt || a.createdAt)
  )
  return { list: merged, total: merged.length }
}

async function onLoad() {
  if (tab.value === 'todo') {
    // 待办一次拉完，无分页
    finished.value = true
    loading.value = false
    return
  }
  try {
    const { list, total } = await fetchMine()
    rows.value.push(...list)
    current.value += 1
    finished.value = rows.value.length >= total
  } finally {
    loading.value = false
  }
}

async function onRefresh() {
  refreshing.value = true
  try {
    current.value = 1
    rows.value = []
    if (tab.value === 'todo') {
      const { list } = await fetchTodo()
      rows.value = list
      finished.value = true
    } else {
      const { list, total } = await fetchMine()
      rows.value = list
      current.value = 2
      finished.value = rows.value.length >= total
    }
  } finally {
    refreshing.value = false
  }
}

onMounted(onRefresh)
</script>

<style scoped>
.triage-entry {
  font-size: 13px;
  color: #fff;
}

/* 需求卡片（对齐原型 demand-item） */
.demand-item {
  background: #fff;
  border-radius: 12px;
  margin: 10px 12px;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.demand-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.demand-no {
  font-size: 12px;
  color: #888;
}

.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 8px;
  white-space: nowrap;
}

.demand-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.type-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.title-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hold-tag {
  background: #fef3c7;
  color: #b45309;
  flex-shrink: 0;
}

.demand-meta {
  font-size: 12px;
  color: #999;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.meta-left {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.meta-right {
  flex-shrink: 0;
  font-weight: 600;
}
</style>
