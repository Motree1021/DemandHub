<template>
  <app-layout title="待受理队列" show-back>
    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list
        v-model:loading="loading"
        :finished="finished"
        finished-text="没有更多了"
        :immediate-check="false"
        @load="onLoad"
      >
        <div v-for="d in rows" :key="d.id" class="demand-item">
          <div @click="router.push(`/demand/${d.id}`)">
            <div class="demand-top">
              <span class="demand-no">{{ d.demandNo }}</span>
              <span class="tag" :style="tagStyle(statusMeta(d.status))">{{ statusLabel(d.status) }}</span>
            </div>
            <div class="demand-title">
              <span class="tag type-tag" :style="tagStyle(typeMeta(d.demandTypeCode))">{{ typeShortLabel(d.demandTypeCode) }}</span>
              <span class="title-text">{{ d.title }}</span>
            </div>
            <div class="demand-meta">
              <span class="meta-left">期望交付：{{ d.expectDeliveryAt ? fmtDate(d.expectDeliveryAt) : '-' }}</span>
              <span class="meta-right" :style="{ color: urgencyMeta(d.urgency).color }">{{ urgencyLabel(d.urgency) }}</span>
            </div>
          </div>
          <!-- 快捷操作（≥44px 触控区） -->
          <div class="quick-ops">
            <van-button size="small" type="primary" class="op-btn" @click="openDialog('ACCEPT', d)">受理</van-button>
            <van-button size="small" type="warning" plain class="op-btn" @click="openDialog('RETURN', d)">退回</van-button>
            <van-button size="small" type="danger" plain class="op-btn" @click="openDialog('CLOSE', d)">关闭</van-button>
          </div>
        </div>
        <van-empty v-if="finished && !rows.length" description="待受理队列已清空" />
      </van-list>
    </van-pull-refresh>

    <!-- 意见输入弹窗 -->
    <van-dialog
      v-model:show="dlg.visible"
      :title="dlg.title"
      show-cancel-button
      :before-close="onDialogBeforeClose"
    >
      <div class="dlg-body">
        <van-field
          v-model="dlg.comment"
          type="textarea"
          rows="3"
          maxlength="500"
          :placeholder="dlg.placeholder"
        />
      </div>
    </van-dialog>
  </app-layout>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast, showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import { triageQueue, acceptDemand, returnDemand, closeDemand, type DemandEntity } from '@/api/demand'
import { statusLabel, statusMeta, typeMeta, typeShortLabel, urgencyLabel, urgencyMeta, fmtDate, type ColorMeta } from '@/utils/format'

const router = useRouter()

const PAGE_SIZE = 10

const rows = ref<DemandEntity[]>([])
const current = ref(1)
const loading = ref(false)
const refreshing = ref(false)
const finished = ref(false)

const dlg = reactive({
  visible: false,
  action: '',
  demandId: 0,
  title: '',
  placeholder: '',
  required: false,
  comment: ''
})

function tagStyle(m: ColorMeta) {
  return { background: m.bg, color: m.color }
}

async function fetchPage(): Promise<void> {
  const data = await triageQueue({ current: current.value, size: PAGE_SIZE })
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
  } finally {
    refreshing.value = false
  }
}

const ACTION_META: Record<string, { label: string; required: boolean; placeholder: string }> = {
  ACCEPT: { label: '受理需求', required: false, placeholder: '受理意见（选填）' },
  RETURN: { label: '退回补充', required: true, placeholder: '退回原因（必填）' },
  CLOSE: { label: '关闭需求', required: true, placeholder: '关闭原因（必填）' }
}

function openDialog(action: string, d: DemandEntity) {
  const meta = ACTION_META[action]
  dlg.visible = true
  dlg.action = action
  dlg.demandId = d.id
  dlg.title = `${meta.label} · ${d.demandNo}`
  dlg.placeholder = meta.placeholder
  dlg.required = meta.required
  dlg.comment = ''
}

function onDialogBeforeClose(action: string): boolean {
  if (action !== 'confirm') {
    return true
  }
  if (dlg.required && !dlg.comment.trim()) {
    showToast(dlg.placeholder)
    return false
  }
  runAction()
  return true
}

async function runAction() {
  const comment = dlg.comment.trim()
  switch (dlg.action) {
    case 'ACCEPT':
      await acceptDemand(dlg.demandId, comment || undefined)
      break
    case 'RETURN':
      await returnDemand(dlg.demandId, comment)
      break
    case 'CLOSE':
      await closeDemand(dlg.demandId, comment)
      break
  }
  showSuccessToast('操作成功')
  await onRefresh()
}

onMounted(onRefresh)
</script>

<style scoped>
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

.quick-ops {
  display: flex;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f5f5f5;
}

.op-btn {
  flex: 1;
  min-height: 44px;
  border-radius: 8px;
}

.dlg-body {
  padding: 8px 16px 16px;
}
</style>
