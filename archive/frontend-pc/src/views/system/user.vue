<template>
  <div class="user-page">
    <el-card>
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="姓名 / 登录账号 / 工号"
          clearable
          style="width: 240px"
          @keyup.enter="load(1)"
          @clear="load(1)"
        />
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 160px" @change="load(1)">
          <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <el-button type="primary" @click="load(1)">查询</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="姓名" width="110" />
        <el-table-column label="登录账号" width="130">
          <template #default="{ row }">{{ row.loginName || '—' }}</template>
        </el-table-column>
        <el-table-column label="部门" min-width="180">
          <template #default="{ row }">{{ row.deptPath || (row.primaryOrgId ?? '—') }}</template>
        </el-table-column>
        <el-table-column label="手机" width="130">
          <template #default="{ row }">{{ row.phone || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最后登录" width="190">
          <template #default="{ row }">
            <span v-if="row.lastLoginAt">{{ row.lastLoginChannel || '—' }} · {{ fmtTime(row.lastLoginAt) }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-dropdown trigger="click" @command="onCommand($event, row)">
              <el-button link type="primary">
                更多<el-icon><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="row.status === 'PENDING'" command="complete">补全</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'DISABLED' || row.status === 'PENDING'" command="activate">激活</el-dropdown-item>
                  <el-dropdown-item v-if="row.status === 'ACTIVE'" command="disable">停用</el-dropdown-item>
                  <el-dropdown-item command="loginAccount">设登录账号</el-dropdown-item>
                  <el-dropdown-item command="resetPassword">重置密码</el-dropdown-item>
                  <el-dropdown-item command="mappings">渠道映射</el-dropdown-item>
                  <el-dropdown-item command="merge">合并</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
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

    <!-- 详情 -->
    <el-dialog v-model="detailVisible" title="用户详情" width="720px">
      <el-descriptions v-loading="detailLoading" :column="2" border>
        <el-descriptions-item label="ID">{{ detail?.id }}</el-descriptions-item>
        <el-descriptions-item label="用户标识">{{ detail?.userId }}</el-descriptions-item>
        <el-descriptions-item label="姓名">{{ detail?.name }}</el-descriptions-item>
        <el-descriptions-item label="登录账号">{{ detail?.loginName || '—' }}</el-descriptions-item>
        <el-descriptions-item label="手机">{{ detail?.phone || '—' }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ detail?.email || '—' }}</el-descriptions-item>
        <el-descriptions-item label="工号">{{ detail?.employeeNo || '—' }}</el-descriptions-item>
        <el-descriptions-item label="企微ID">{{ detail?.wecomId || '—' }}</el-descriptions-item>
        <el-descriptions-item label="是否员工">{{ employeeLabel(detail?.isEmployee) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag v-if="detail" :type="statusTagType(detail.status)">{{ statusLabel(detail.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="主组织">{{ detail?.deptPath || detail?.primaryOrgId || '—' }}</el-descriptions-item>
        <el-descriptions-item label="合并至用户">{{ detail?.mergedToUserId ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="最后登录渠道">{{ detail?.lastLoginChannel || '—' }}</el-descriptions-item>
        <el-descriptions-item label="最后登录时间">{{ fmtTime(detail?.lastLoginAt) }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ fmtTime(detail?.createdAt) }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 补全 -->
    <el-dialog v-model="completeVisible" title="补全并激活用户" width="520px">
      <el-form :model="completeForm" label-width="110px">
        <el-form-item label="姓名" required>
          <el-input v-model="completeForm.name" placeholder="姓名" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="completeForm.phone" placeholder="手机" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="completeForm.email" placeholder="邮箱" />
        </el-form-item>
        <el-form-item label="工号">
          <el-input v-model="completeForm.employeeNo" placeholder="工号" />
        </el-form-item>
        <el-form-item label="主组织">
          <el-tree-select
            v-model="completeForm.primaryOrgId"
            :data="orgOptions"
            :props="{ label: 'name', value: 'orgId', children: 'children' }"
            check-strictly
            clearable
            placeholder="选择主组织"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="completeVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCompleteSave">保存并激活</el-button>
      </template>
    </el-dialog>

    <!-- 设登录账号 -->
    <el-dialog v-model="loginVisible" title="设置登录账号" width="440px">
      <el-form label-width="90px">
        <el-form-item label="登录账号" required>
          <el-input v-model="loginForm.loginName" placeholder="3~64 位字母、数字、_ . -" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loginVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onLoginAccountSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 重置密码 -->
    <el-dialog v-model="pwdVisible" title="重置密码" width="440px">
      <el-form label-width="90px">
        <el-form-item label="新密码" required>
          <el-input v-model="pwdForm.newPassword" type="password" show-password placeholder="至少 8 位，需含字母和数字" />
        </el-form-item>
      </el-form>
      <el-alert type="warning" :closable="false" title="重置后该用户下次登录需强制改密" />
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onResetPasswordSave">重置</el-button>
      </template>
    </el-dialog>

    <!-- 渠道映射 -->
    <el-dialog v-model="mappingsVisible" title="渠道映射" width="860px">
      <el-table :data="mappings" v-loading="mappingsLoading" border>
        <el-table-column prop="channelCode" label="渠道" width="100" />
        <el-table-column prop="channelUserId" label="渠道用户ID" width="140" />
        <el-table-column label="渠道姓名" width="110">
          <template #default="{ row }">{{ row.channelName || '—' }}</template>
        </el-table-column>
        <el-table-column label="渠道手机" width="130">
          <template #default="{ row }">{{ row.channelPhone || '—' }}</template>
        </el-table-column>
        <el-table-column label="渠道部门" min-width="140">
          <template #default="{ row }">{{ row.channelDept || '—' }}</template>
        </el-table-column>
        <el-table-column prop="matchType" label="匹配方式" width="110" />
        <el-table-column label="绑定时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.boundAt) }}</template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 合并 -->
    <el-dialog v-model="mergeVisible" title="合并用户" width="560px">
      <el-form label-width="90px">
        <el-form-item label="源用户" required>
          <div class="merge-source">
            <el-select
              v-model="mergeForm.sourceUserId"
              filterable
              remote
              clearable
              :remote-method="searchSourceUsers"
              :loading="mergeUserLoading"
              placeholder="输入姓名搜索（数据将迁出）"
              style="flex: 1"
              @change="previewData = null"
            >
              <el-option v-for="u in sourceOptions" :key="u.id" :value="u.id" :label="`${u.name}（${u.userId}）`" />
            </el-select>
            <el-button :disabled="!mergeForm.sourceUserId" :loading="previewLoading" @click="onPreview">预览影响</el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="previewData" label="影响预览">
          <el-descriptions :column="2" border size="small" class="preview-desc">
            <el-descriptions-item v-for="(count, key) in previewData" :key="key" :label="String(key)">
              {{ count }} 行
            </el-descriptions-item>
          </el-descriptions>
        </el-form-item>
        <el-form-item label="目标用户" required>
          <el-select
            v-model="mergeForm.targetUserId"
            filterable
            remote
            clearable
            :remote-method="searchTargetUsers"
            :loading="mergeUserLoading"
            placeholder="输入姓名搜索（数据将迁入）"
            style="width: 100%"
          >
            <el-option
              v-for="u in targetOptions.filter((o) => o.id !== mergeForm.sourceUserId)"
              :key="u.id"
              :value="u.id"
              :label="`${u.name}（${u.userId}）`"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <el-alert type="error" :closable="false" title="合并后源用户的全部业务数据将迁至目标用户，源用户置为已合并，该操作不可恢复！" />
      <template #footer>
        <el-button @click="mergeVisible = false">取消</el-button>
        <el-button type="danger" :loading="saving" :disabled="!mergeForm.sourceUserId || !mergeForm.targetUserId" @click="onMergeConfirm">
          确认合并
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { pageUsers, orgTree } from '@/api/grant'
import type { UserSnapshotVO, OrgNode } from '@/api/grant'
import {
  pageAdminUsers,
  getUserDetail,
  completeUser,
  activateUser,
  disableUser,
  mergePreview,
  mergeUsers,
  userMappings,
  setLoginAccount,
  resetPassword
} from '@/api/system'
import type { AdminUser, ChannelMapping, CompleteUserRequest } from '@/api/system'
import { fmtTime } from '@/utils/format'

const statusOptions = [
  { label: '待补全', value: 'PENDING' },
  { label: '正常', value: 'ACTIVE' },
  { label: '已停用', value: 'DISABLED' },
  { label: '已合并', value: 'MERGED' }
]

const STATUS_META: Record<string, { label: string; type: 'success' | 'warning' | 'info' | 'danger' }> = {
  ACTIVE: { label: '正常', type: 'success' },
  PENDING: { label: '待补全', type: 'warning' },
  DISABLED: { label: '已停用', type: 'info' },
  MERGED: { label: '已合并', type: 'danger' }
}

const LOGIN_NAME_RE = /^[A-Za-z0-9_.-]{3,64}$/

const query = reactive({ current: 1, size: 10, keyword: '', status: '' })
const rows = ref<AdminUser[]>([])
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const currentRow = ref<AdminUser | null>(null)
const orgOptions = ref<OrgNode[]>([])

function statusLabel(status: string) {
  return STATUS_META[status]?.label || status
}

function statusTagType(status: string) {
  return STATUS_META[status]?.type || 'info'
}

function employeeLabel(v: number | null | undefined) {
  if (v == null) return '—'
  return v === 1 ? '是' : '否'
}

async function load(current = query.current) {
  query.current = current
  loading.value = true
  try {
    const data = await pageAdminUsers({
      current: query.current,
      size: query.size,
      keyword: query.keyword || undefined,
      status: query.status || undefined
    })
    rows.value = data.records
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onCommand(cmd: string | number | object, row: AdminUser) {
  switch (cmd) {
    case 'complete':
      openComplete(row)
      break
    case 'activate':
      onActivate(row)
      break
    case 'disable':
      onDisable(row)
      break
    case 'loginAccount':
      openLoginAccount(row)
      break
    case 'resetPassword':
      openResetPassword(row)
      break
    case 'mappings':
      openMappings(row)
      break
    case 'merge':
      openMerge(row)
      break
  }
}

/* ---------- 详情 ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<AdminUser | null>(null)

async function openDetail(row: AdminUser) {
  currentRow.value = row
  detail.value = row
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getUserDetail(row.id)
  } finally {
    detailLoading.value = false
  }
}

/* ---------- 补全 ---------- */
const completeVisible = ref(false)
const completeForm = reactive<CompleteUserRequest>({ name: '', phone: '', email: '', employeeNo: '', primaryOrgId: null })

function openComplete(row: AdminUser) {
  currentRow.value = row
  Object.assign(completeForm, {
    name: row.name || '',
    phone: row.phone || '',
    email: row.email || '',
    employeeNo: row.employeeNo || '',
    primaryOrgId: row.primaryOrgId ?? null
  })
  completeVisible.value = true
}

async function onCompleteSave() {
  if (!completeForm.name?.trim()) {
    ElMessage.warning('请填写姓名')
    return
  }
  saving.value = true
  try {
    await completeUser(currentRow.value!.id, {
      name: completeForm.name.trim(),
      phone: completeForm.phone || null,
      email: completeForm.email || null,
      employeeNo: completeForm.employeeNo || null,
      primaryOrgId: completeForm.primaryOrgId ?? null
    })
    ElMessage.success('已补全并激活')
    completeVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

/* ---------- 激活 / 停用 ---------- */
async function onActivate(row: AdminUser) {
  await activateUser(row.id)
  ElMessage.success('已激活')
  load()
}

async function onDisable(row: AdminUser) {
  await ElMessageBox.confirm(`确认停用用户「${row.name}」？停用后将无法登录`, '停用确认', {
    type: 'warning',
    confirmButtonText: '停用',
    cancelButtonText: '取消'
  })
  await disableUser(row.id)
  ElMessage.success('已停用')
  load()
}

/* ---------- 设登录账号 ---------- */
const loginVisible = ref(false)
const loginForm = reactive({ loginName: '' })

function openLoginAccount(row: AdminUser) {
  currentRow.value = row
  loginForm.loginName = row.loginName || ''
  loginVisible.value = true
}

async function onLoginAccountSave() {
  const loginName = loginForm.loginName.trim()
  if (!LOGIN_NAME_RE.test(loginName)) {
    ElMessage.warning('登录账号需为 3~64 位字母、数字、_ . -')
    return
  }
  saving.value = true
  try {
    await setLoginAccount(currentRow.value!.id, loginName)
    ElMessage.success('已设置登录账号')
    loginVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

/* ---------- 重置密码 ---------- */
const pwdVisible = ref(false)
const pwdForm = reactive({ newPassword: '' })

function openResetPassword(row: AdminUser) {
  currentRow.value = row
  pwdForm.newPassword = ''
  pwdVisible.value = true
}

async function onResetPasswordSave() {
  const pwd = pwdForm.newPassword
  if (pwd.length < 8 || !/[A-Za-z]/.test(pwd) || !/\d/.test(pwd)) {
    ElMessage.warning('新密码至少 8 位，且需同时包含字母和数字')
    return
  }
  saving.value = true
  try {
    await resetPassword(currentRow.value!.id, pwd)
    ElMessage.success('密码已重置，该用户下次登录需强制改密')
    pwdVisible.value = false
  } finally {
    saving.value = false
  }
}

/* ---------- 渠道映射 ---------- */
const mappingsVisible = ref(false)
const mappingsLoading = ref(false)
const mappings = ref<ChannelMapping[]>([])

async function openMappings(row: AdminUser) {
  currentRow.value = row
  mappingsVisible.value = true
  mappingsLoading.value = true
  try {
    mappings.value = await userMappings(row.id)
  } finally {
    mappingsLoading.value = false
  }
}

/* ---------- 合并 ---------- */
const mergeVisible = ref(false)
const mergeUserLoading = ref(false)
const previewLoading = ref(false)
const mergeForm = reactive<{ sourceUserId: number | null; targetUserId: number | null }>({
  sourceUserId: null,
  targetUserId: null
})
const sourceOptions = ref<UserSnapshotVO[]>([])
const targetOptions = ref<UserSnapshotVO[]>([])
const previewData = ref<Record<string, number> | null>(null)

function openMerge(row: AdminUser) {
  mergeForm.sourceUserId = row.id
  mergeForm.targetUserId = null
  sourceOptions.value = [row]
  targetOptions.value = []
  previewData.value = null
  mergeVisible.value = true
}

async function searchSourceUsers(keyword: string) {
  mergeUserLoading.value = true
  try {
    const data = await pageUsers({ current: 1, size: 20, keyword: keyword || undefined })
    sourceOptions.value = data.records
  } finally {
    mergeUserLoading.value = false
  }
}

async function searchTargetUsers(keyword: string) {
  mergeUserLoading.value = true
  try {
    const data = await pageUsers({ current: 1, size: 20, keyword: keyword || undefined })
    targetOptions.value = data.records
  } finally {
    mergeUserLoading.value = false
  }
}

async function onPreview() {
  if (!mergeForm.sourceUserId) return
  previewLoading.value = true
  try {
    previewData.value = await mergePreview(mergeForm.sourceUserId)
  } finally {
    previewLoading.value = false
  }
}

async function onMergeConfirm() {
  if (!mergeForm.sourceUserId || !mergeForm.targetUserId) return
  await ElMessageBox.confirm('合并后源用户全部业务数据将迁至目标用户，且不可恢复。确认合并？', '合并确认', {
    type: 'error',
    confirmButtonText: '确认合并',
    cancelButtonText: '取消'
  })
  saving.value = true
  try {
    await mergeUsers({ sourceUserId: mergeForm.sourceUserId, targetUserId: mergeForm.targetUserId })
    ElMessage.success('合并完成')
    mergeVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  load(1)
  orgOptions.value = await orgTree()
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

.merge-source {
  display: flex;
  gap: 8px;
  width: 100%;
}

.preview-desc {
  width: 100%;
}
</style>
