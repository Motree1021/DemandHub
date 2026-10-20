<template>
  <el-card>
    <div class="toolbar">
      <el-select v-model="query.status" placeholder="状态" clearable class="sel" @change="load(1)">
        <el-option v-for="s in FLOW_STATUS_OPTIONS" :key="s" :label="statusLabel(s)" :value="s" />
      </el-select>
      <el-select v-model="query.urgency" placeholder="紧急度" clearable class="sel" @change="load(1)">
        <el-option v-for="(m, k) in URGENCY_META" :key="k" :label="m.label" :value="k" />
      </el-select>
      <el-select v-model="query.typeCode" placeholder="类型" clearable class="sel" @change="load(1)">
        <el-option v-for="(label, k) in TYPE_META" :key="k" :label="label" :value="k" />
      </el-select>
      <el-button type="primary" @click="load(1)">查询</el-button>
      <!-- 草稿是提报人私有编辑态（2026-10-20 拍板）：默认隐藏，开关按需查看 -->
      <el-switch v-model="query.includeDrafts" active-text="含草稿" @change="load(1)" />
    </div>

    <el-table :data="rows" v-loading="loading" stripe @row-click="goDetail">
      <el-table-column label="编号" width="170">
        <template #default="{ row }">{{ row.demandNo || (row.status === 'DRAFT' ? `草稿 #${row.id}` : '—') }}</template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
      <el-table-column label="类型" width="110">
        <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
      </el-table-column>
      <el-table-column label="紧急度" width="90">
        <template #default="{ row }"><UrgencyTag :urgency="row.urgency" /></template>
      </el-table-column>
      <el-table-column label="状态" width="150">
        <template #default="{ row }">
          <StatusTag :status="row.status" :on-hold="row.onHold" :hold-reason="row.holdReason" />
        </template>
      </el-table-column>
      <el-table-column prop="submitterName" label="提报人" width="100" />
      <el-table-column label="处理人" width="100">
        <template #default="{ row }">{{ row.assigneeName || '—' }}</template>
      </el-table-column>
      <el-table-column prop="submittedAt" label="提交时间" width="165" />
      <el-table-column prop="updatedAt" label="更新时间" width="165" />
    </el-table>
    <el-pagination class="pager" layout="total, sizes, prev, pager, next, jumper" :total="total"
                   :page-sizes="[10, 20, 50, 100]" :page-size="query.size" :current-page="query.page"
                   @current-change="load" @size-change="onSizeChange" />
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { triageApi } from '@/api'
import type { DemandRow } from '@/api'
import { ApiError } from '@/api/request'
import { FLOW_STATUS_OPTIONS, statusLabel, URGENCY_META, TYPE_META, typeLabel } from '@/utils/status'
import StatusTag from '@/components/StatusTag.vue'
import UrgencyTag from '@/components/UrgencyTag.vue'
const router = useRouter()
const loading = ref(false)
const rows = ref<DemandRow[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 20, status: '', urgency: '', typeCode: '', includeDrafts: false })

/** 每页条数变化：回到第 1 页重新查询，避免"大页码 × 大页容"越界空页 */
function onSizeChange(size: number) {
  query.size = size
  load(1)
}

async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const data = await triageApi.demands({
      page: query.page, size: query.size,
      status: query.status || undefined,
      urgency: query.urgency || undefined,
      typeCode: query.typeCode || undefined,
      includeDrafts: query.includeDrafts || undefined,
    })
    rows.value = data.records
    total.value = data.total
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function goDetail(row: DemandRow) {
  router.push(`/demands/${row.id}`)
}

onMounted(() => load(1))
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.sel { width: 150px; }
.pager { margin-top: 16px; justify-content: flex-end; }
:deep(.el-table__row) { cursor: pointer; }
</style>
