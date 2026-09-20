<template>
  <div class="grant-page">
    <el-card>
      <div class="toolbar">
        <el-input v-model="query.userId" placeholder="用户ID" clearable style="width: 180px" @keyup.enter="load(1)" />
        <el-select v-model="query.roleCode" placeholder="角色" clearable style="width: 180px">
          <el-option v-for="r in roleOptions" :key="r.value" :label="r.label" :value="r.value" />
        </el-select>
        <el-button type="primary" @click="load(1)">查询</el-button>
        <el-button type="primary" plain @click="openEdit()">新增授权</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="userId" label="用户ID" width="150" />
        <el-table-column prop="roleCode" label="角色" width="150">
          <template #default="{ row }">{{ roleLabel(row.roleCode) }}</template>
        </el-table-column>
        <el-table-column label="组织范围" min-width="160">
          <template #default="{ row }">{{ row.orgId == null ? '全部组织' : orgName(row.orgId) }}</template>
        </el-table-column>
        <el-table-column label="需求类型范围" width="130">
          <template #default="{ row }">{{ row.demandTypeScope || '全部' }}</template>
        </el-table-column>
        <el-table-column label="生效期" width="200">
          <template #default="{ row }">
            <span v-if="!row.effectiveFrom && !row.effectiveTo">长期有效</span>
            <span v-else>{{ fmtTime(row.effectiveFrom) }} ~ {{ fmtTime(row.effectiveTo) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="grantedBy" label="授权人" width="110" />
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确认删除该授权？用户会话将立即失效" @confirm="onDelete(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="query.size"
        :current-page="query.current"
        @current-change="load"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑授权' : '新增授权'" width="520px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="用户" required>
          <el-select
            v-model="form.userId"
            filterable
            remote
            :remote-method="searchUsers"
            :loading="userLoading"
            placeholder="输入姓名/用户ID搜索"
            style="width: 100%"
            @focus="searchUsers('')"
          >
            <el-option v-for="u in userOptions" :key="u.userId" :value="u.userId" :label="`${u.name}（${u.userId}）`" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色" required>
          <el-select v-model="form.roleCode" style="width: 100%">
            <el-option v-for="r in roleOptions" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="组织范围">
          <el-tree-select
            v-model="form.orgId"
            :data="orgOptions"
            :props="{ label: 'name', value: 'orgId', children: 'children' }"
            check-strictly
            clearable
            placeholder="不选表示全部组织"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="需求类型范围">
          <el-select v-model="form.demandTypeScope" clearable placeholder="不选表示全部类型" style="width: 100%">
            <el-option label="科技需求" value="TECH" />
            <el-option label="物料需求" value="MATL" />
            <el-option label="培训需求" value="TRAIN" />
          </el-select>
        </el-form-item>
        <el-form-item label="生效期">
          <el-date-picker
            v-model="effectiveRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="生效时间"
            end-placeholder="失效时间"
            style="width: 100%"
            value-format="YYYY-MM-DDTHH:mm:ss"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { pageGrants, createGrant, updateGrant, deleteGrant, pageUsers, orgTree } from '@/api/grant'
import type { RoleGrant, RoleGrantSaveRequest, UserSnapshotVO, OrgNode } from '@/api/grant'

const roleOptions = [
  { label: '系统管理员', value: 'ADMIN' },
  { label: '管理层', value: 'EXECUTIVE' },
  { label: '需求管理员', value: 'DEMAND_MANAGER' },
  { label: '承接人', value: 'HANDLER' },
  { label: '提报人', value: 'REPORTER' }
]

const query = reactive({ current: 1, size: 10, userId: '', roleCode: '' })
const rows = ref<RoleGrant[]>([])
const total = ref(0)
const loading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<RoleGrantSaveRequest>({ userId: '', roleCode: '', orgId: null, demandTypeScope: null })
const effectiveRange = ref<[string, string] | null>(null)

const userOptions = ref<UserSnapshotVO[]>([])
const userLoading = ref(false)
const orgOptions = ref<OrgNode[]>([])
const orgNameMap = ref<Record<number, string>>({})

function roleLabel(code: string) {
  return roleOptions.find((r) => r.value === code)?.label || code
}

function orgName(orgId: number) {
  return orgNameMap.value[orgId] || String(orgId)
}

function fmtTime(t: string | null) {
  return t ? t.replace('T', ' ').slice(0, 16) : '—'
}

async function load(current = query.current) {
  query.current = current
  loading.value = true
  try {
    const data = await pageGrants({
      current: query.current,
      size: query.size,
      userId: query.userId || undefined,
      roleCode: query.roleCode || undefined
    })
    rows.value = data.records
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function searchUsers(keyword: string) {
  userLoading.value = true
  try {
    const data = await pageUsers({ current: 1, size: 20, keyword: keyword || undefined })
    userOptions.value = data.records
  } finally {
    userLoading.value = false
  }
}

function collectOrgNames(nodes: OrgNode[]) {
  nodes.forEach((n) => {
    orgNameMap.value[n.orgId] = n.name
    if (n.children) collectOrgNames(n.children)
  })
}

function openEdit(row?: RoleGrant) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      userId: row.userId,
      roleCode: row.roleCode,
      orgId: row.orgId,
      demandTypeScope: row.demandTypeScope
    })
    effectiveRange.value = row.effectiveFrom || row.effectiveTo ? [row.effectiveFrom || '', row.effectiveTo || ''] : null
  } else {
    Object.assign(form, { id: undefined, userId: '', roleCode: '', orgId: null, demandTypeScope: null })
    effectiveRange.value = null
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.userId || !form.roleCode) {
    ElMessage.warning('请选择用户与角色')
    return
  }
  form.effectiveFrom = effectiveRange.value?.[0] || null
  form.effectiveTo = effectiveRange.value?.[1] || null
  saving.value = true
  try {
    if (form.id) {
      await updateGrant(form.id, form)
    } else {
      await createGrant(form)
    }
    ElMessage.success('已保存，目标用户会话已失效（刷新令牌自动续期）')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function onDelete(id: number) {
  await deleteGrant(id)
  ElMessage.success('已删除')
  load()
}

onMounted(async () => {
  load(1)
  const tree = await orgTree()
  orgOptions.value = tree
  collectOrgNames(tree)
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
