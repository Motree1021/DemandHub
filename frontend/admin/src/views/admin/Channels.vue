<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>渠道注册</span>
          <span class="tip">渠道由系统登记，这里只管启用/停用；对接参数由运维在环境配置维护。</span>
        </div>
      </template>
      <el-table :data="channels" v-loading="loadingChannels">
        <el-table-column prop="channelCode" label="渠道码" width="160" />
        <el-table-column prop="channelName" label="渠道名称" width="160" />
        <el-table-column prop="appId" label="应用 ID" width="140">
          <template #default="{ row }">{{ row.appId || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="170" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link :type="row.status === 'ACTIVE' ? 'warning' : 'success'" @click="onToggle(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="unmapped-card">
      <template #header>
        <div class="card-header">
          <span>部门未映射校准</span>
          <span class="tip">渠道用户登录时部门对不上公司架构会记录在这里；在组织管理补好映射后，删除对应记录即可。</span>
        </div>
      </template>
      <div class="toolbar">
        <el-select v-model="filterChannel" placeholder="全部渠道" clearable style="width: 200px" @change="loadUnmapped">
          <el-option v-for="c in channels" :key="c.channelCode" :label="`${c.channelName}（${c.channelCode}）`" :value="c.channelCode" />
        </el-select>
      </div>
      <el-table :data="unmapped" v-loading="loadingUnmapped">
        <el-table-column prop="channelCode" label="渠道码" width="150" />
        <el-table-column prop="deptId" label="渠道部门 ID" width="130" />
        <el-table-column prop="deptName" label="部门名称" min-width="140">
          <template #default="{ row }">{{ row.deptName || '-' }}</template>
        </el-table-column>
        <el-table-column prop="deptPath" label="部门路径" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.deptPath || '-' }}</template>
        </el-table-column>
        <el-table-column prop="hitCount" label="命中次数" width="90" sortable />
        <el-table-column prop="lastSeenAt" label="最近出现" width="170" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { channelApi } from '@/api'
import type { ChannelRow, DeptUnmappedRow } from '@/api'

const channels = ref<ChannelRow[]>([])
const unmapped = ref<DeptUnmappedRow[]>([])
const filterChannel = ref<string>()
const loadingChannels = ref(false)
const loadingUnmapped = ref(false)

async function loadChannels() {
  loadingChannels.value = true
  try {
    channels.value = await channelApi.list()
  } finally {
    loadingChannels.value = false
  }
}

async function loadUnmapped() {
  loadingUnmapped.value = true
  try {
    unmapped.value = await channelApi.unmapped(filterChannel.value || undefined)
  } finally {
    loadingUnmapped.value = false
  }
}

async function onToggle(row: ChannelRow) {
  const next = row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE'
  if (next === 'DISABLED') {
    await ElMessageBox.confirm(
      `停用后「${row.channelName}」渠道的新登录/提报将不可用，确认停用？`, '停用确认', { type: 'warning' })
  }
  await channelApi.updateStatus(row.id, next)
  ElMessage.success(next === 'DISABLED' ? '已停用' : '已启用')
  await loadChannels()
}

async function onRemove(row: DeptUnmappedRow) {
  await ElMessageBox.confirm(
    `确认删除「${row.channelCode} / ${row.deptName || row.deptId}」的未映射记录？请确认已在组织管理中补好映射。`,
    '删除确认', { type: 'warning' })
  await channelApi.removeUnmapped(row.id)
  ElMessage.success('已删除')
  await loadUnmapped()
}

onMounted(async () => {
  await loadChannels()
  await loadUnmapped()
})
</script>

<style scoped>
.card-header { display: flex; align-items: center; gap: 12px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; font-weight: normal; }
.unmapped-card { margin-top: 16px; }
</style>
