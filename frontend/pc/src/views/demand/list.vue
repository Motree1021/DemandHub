<template>
  <div class="list-page">
    <el-card shadow="never">
      <!-- 多 tab：按角色显隐 -->
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="我的提报" name="mine" />
        <el-tab-pane v-if="canSeeOrg" label="本组织承接" name="org" />
        <el-tab-pane v-if="userStore.roles.includes('EXECUTIVE') || userStore.isAdmin" label="全部需求" name="all" />
      </el-tabs>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-select v-model="query.demandTypeCode" placeholder="全部类型" clearable style="width: 140px">
          <el-option v-for="t in typeList" :key="t.typeCode" :label="t.typeName" :value="t.typeCode" />
        </el-select>
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 150px">
          <el-option v-for="(meta, code) in STATUS_META" :key="code" :label="meta.label" :value="code" />
        </el-select>
        <el-select v-model="query.urgency" placeholder="全部紧急程度" clearable style="width: 130px">
          <el-option label="普通" value="NORMAL" />
          <el-option label="紧急" value="URGENT" />
          <el-option label="特急" value="CRITICAL" />
        </el-select>
        <el-select v-model="query.onHold" placeholder="挂起状态" clearable style="width: 110px">
          <el-option label="正常" :value="0" />
          <el-option label="已挂起" :value="1" />
        </el-select>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          start-placeholder="提交开始"
          end-placeholder="提交结束"
          value-format="YYYY-MM-DD"
          style="width: 240px"
        />
        <el-input v-model="query.keyword" placeholder="搜索编号 / 标题" clearable style="width: 200px" @keyup.enter="load(1)" />
        <el-button type="primary" @click="load(1)">查询</el-button>
        <el-button @click="onReset">重置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border stripe @sort-change="onSortChange">
        <el-table-column label="编号" width="170">
          <template #default="{ row }">
            <el-link type="primary" @click="goDetail(row.id)">{{ row.demandNo }}</el-link>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">{{ typeLabel(row.demandTypeCode, row.typeName) }}</template>
        </el-table-column>
        <el-table-column label="提报人" width="100">
          <template #default="{ row }">{{ row.submitterName || '-' }}</template>
        </el-table-column>
        <el-table-column label="承接组织" width="130">
          <template #default="{ row }">{{ row.assigneeOrgName || '-' }}</template>
        </el-table-column>
        <el-table-column label="处理人" width="100">
          <template #default="{ row }">{{ row.assigneeUserName || '未分派' }}</template>
        </el-table-column>
        <el-table-column label="紧急" width="80">
          <template #default="{ row }">
            <el-tag :type="urgencyTagType(row.urgency)" size="small">{{ urgencyLabel(row.urgency) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            <el-tag v-if="row.onHold === 1" type="danger" size="small" style="margin-left: 4px">挂起</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="150" prop="submittedAt" sortable="custom" :sort-orders="['descending', 'ascending']">
          <template #default="{ row }">{{ fmtTime(row.submittedAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDetail(row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, sizes, prev, pager, next, jumper"
        :total="total"
        :page-size="query.size"
        :page-sizes="[10, 20, 50]"
        :current-page="query.current"
        @current-change="load"
        @size-change="onSizeChange"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { pageDemands, type DemandListItem } from '@/api/demand'
import { listActiveTypes, type DemandTypeItem } from '@/api/directory'
import { useUserStore } from '@/store/modules/user'
import { STATUS_META, statusLabel, statusTagType, urgencyLabel, urgencyTagType, typeLabel, fmtTime } from '@/utils/format'

const router = useRouter()
const userStore = useUserStore()

const activeTab = ref('mine')
const rows = ref<DemandListItem[]>([])
const total = ref(0)
const loading = ref(false)
const typeList = ref<DemandTypeItem[]>([])
const dateRange = ref<[string, string] | null>(null)

const query = reactive({
  current: 1,
  size: 10,
  status: undefined as string | undefined,
  demandTypeCode: undefined as string | undefined,
  urgency: undefined as string | undefined,
  keyword: undefined as string | undefined,
  onHold: undefined as number | undefined
})

/** 提交时间排序方向：后端 submittedOrder 参数（默认 desc） */
const sortOrder = ref<'descending' | 'ascending' | null>(null)

/** 经理/处理人/管理者/管理员可见"本组织承接" */
const canSeeOrg = computed(() =>
  userStore.roles.some((r) => ['DEMAND_MANAGER', 'HANDLER', 'EXECUTIVE', 'ADMIN'].includes(r))
)

async function load(page = query.current) {
  query.current = page
  loading.value = true
  try {
    // tab 视角：mine=我的提报；org=本组织承接（数据权限拦截器自动限定）；all=全部（EXECUTIVE 数据权限 bypass）
    const mine = activeTab.value === 'mine'
    const data = await pageDemands({
      current: query.current,
      size: query.size,
      status: query.status,
      demandTypeCode: query.demandTypeCode,
      urgency: query.urgency,
      keyword: query.keyword,
      onHold: query.onHold,
      mine,
      submittedOrder: sortOrder.value === 'ascending' ? 'asc' : 'desc'
    })
    rows.value = filterByDateRange(data.records)
    total.value = data.total
  } finally {
    loading.value = false
  }
}

/** 时间范围前端过滤（后端暂无该参数，仅对当前页生效提示） */
function filterByDateRange(list: DemandListItem[]): DemandListItem[] {
  if (!dateRange.value || !dateRange.value[0]) {
    return list
  }
  const [start, end] = dateRange.value
  return list.filter((r) => {
    const d = (r.submittedAt || '').slice(0, 10)
    return d >= start && d <= end
  })
}

function onSortChange({ order }: { prop: string; order: 'ascending' | 'descending' | null }) {
  sortOrder.value = order
  load(1)
}

function onTabChange() {
  load(1)
}

function onSizeChange(size: number) {
  query.size = size
  load(1)
}

function onReset() {
  query.status = undefined
  query.demandTypeCode = undefined
  query.urgency = undefined
  query.keyword = undefined
  query.onHold = undefined
  dateRange.value = null
  load(1)
}

function goDetail(id: number) {
  router.push(`/demand/detail/${id}`)
}

onMounted(async () => {
  typeList.value = await listActiveTypes()
  // 纯提报人默认"我的提报"，其他角色默认"本组织承接"
  if (canSeeOrg.value && !userStore.roles.includes('REPORTER')) {
    activeTab.value = 'org'
  }
  load(1)
})
</script>

<style scoped>
.filter-bar {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 14px;
}

.pager {
  margin-top: 14px;
  justify-content: flex-end;
}
</style>
