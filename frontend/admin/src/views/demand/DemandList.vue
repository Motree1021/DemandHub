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
      <el-table-column label="需求层级" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.level" :type="levelMeta(row.level).type" size="small">{{ levelMeta(row.level).label }}</el-tag>
          <span v-else>—</span>
        </template>
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
      <!-- 删除草稿（2026-10-22 拍板）：仅 ADMIN 可见、仅 DRAFT 态可删；@click.stop 避免触发行点击跳详情 -->
      <el-table-column v-if="isAdmin" label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'DRAFT'" type="danger" link size="small"
                     @click.stop="confirmDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination class="pager" layout="total, sizes, prev, pager, next, jumper" :total="total"
                   :page-sizes="[10, 20, 50, 100]" :page-size="query.size" :current-page="query.page"
                   @current-change="load" @size-change="onSizeChange" />
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { demandApi, triageApi } from '@/api'
import type { DemandRow } from '@/api'
import { ApiError } from '@/api/request'
import { useAuthStore } from '@/stores/auth'
import { FLOW_STATUS_OPTIONS, statusLabel, URGENCY_META, TYPE_META, typeLabel, DEMAND_LEVEL_META, demandLevelOf, type DemandLevel } from '@/utils/status'
import StatusTag from '@/components/StatusTag.vue'
import UrgencyTag from '@/components/UrgencyTag.vue'
const router = useRouter()
const auth = useAuthStore()
const isAdmin = computed(() => auth.roles.includes('ADMIN'))
const loading = ref(false)
// level 为前端预计算的需求层级（ext.mode/typeRecognition 组合判定），避免模板里重复判定
const rows = ref<(DemandRow & { level: DemandLevel | null })[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 20, status: '', urgency: '', typeCode: '', includeDrafts: false })

// 插槽 row 为 any，经显式类型签名取值避免 any 直接索引 META
function levelMeta(level: DemandLevel) {
  return DEMAND_LEVEL_META[level]
}

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
    rows.value = data.records.map(row => ({ ...row, level: demandLevelOf(row.ext) }))
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

/** 删除草稿（2026-10-22 拍板③A）：标准确认框 + 固定警示文案，确认后物理删除并重载当前页 */
async function confirmDelete(row: DemandRow) {
  try {
    await ElMessageBox.confirm(
      `确定删除草稿「${row.title || `#${row.id}`}」吗？删除后将无法恢复，请谨慎操作！`,
      '删除草稿',
      { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
  } catch {
    return // 取消/关闭：不操作
  }
  try {
    await demandApi.remove(row.id)
    ElMessage.success('草稿已删除')
    load(query.page)
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '删除失败')
  }
}

onMounted(() => load(1))
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.sel { width: 150px; }
.pager { margin-top: 16px; justify-content: flex-end; }
:deep(.el-table__row) { cursor: pointer; }
</style>
