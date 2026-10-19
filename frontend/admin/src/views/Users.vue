<template>
  <el-card>
    <div class="toolbar">
      <el-input v-model="query.keyword" placeholder="姓名 / 登录账号" clearable class="kw"
                @keyup.enter="load(1)" @clear="load(1)" />
      <el-select v-model="query.role" placeholder="角色" clearable class="sel" @change="load(1)">
        <el-option v-for="r in roleOptions" :key="r.value" :label="r.label" :value="r.value" />
      </el-select>
      <el-select v-model="query.status" placeholder="状态" clearable class="sel" @change="load(1)">
        <el-option label="启用" value="ACTIVE" />
        <el-option label="禁用" value="DISABLED" />
      </el-select>
      <el-button type="primary" @click="load(1)">查询</el-button>
      <el-button type="primary" plain class="add" @click="createVisible = true">新建用户</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="loginAccount" label="登录账号" min-width="150">
        <template #default="{ row }">
          {{ row.loginAccount || '—' }}
          <!-- OneID：该 PC 用户已挂接的渠道身份（渠道钥匙） -->
          <div v-for="item in row.channelIdentities ?? []" :key="`${item.channel}:${item.channelUserId}`"
               class="scope-text">
            渠道：{{ channelLabel(item.channel) }} {{ item.channelUserName }}
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="姓名" min-width="100" />
      <el-table-column prop="wecomUserid" label="企业微信ID" min-width="130">
        <!-- acct: 开头是账密用户的占位编号，非真实企微身份，不展示 -->
        <template #default="{ row }">{{ row.wecomUserid?.startsWith('acct:') ? '—' : row.wecomUserid }}</template>
      </el-table-column>
      <el-table-column label="角色" min-width="160">
        <template #default="{ row }">
          <el-tag v-for="r in row.roles" :key="r" size="small" :type="roleTagType(r)" class="role-tag">
            {{ roleLabel(r) }}
          </el-tag>
          <!-- 业务角色的需求类型权限（空=无权限，什么都看不到） -->
          <div v-if="row.typeScope?.length" class="scope-text">类型：{{ scopeText(row.typeScope) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'ACTIVE' ? 'success' : 'warning'">
            {{ row.status === 'ACTIVE' ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="phone" label="手机" min-width="120">
        <template #default="{ row }">{{ row.phone || '—' }}</template>
      </el-table-column>
      <el-table-column prop="email" label="邮箱" min-width="150">
        <template #default="{ row }">{{ row.email || '—' }}</template>
      </el-table-column>
      <el-table-column prop="lastLoginAt" label="最近登录" min-width="150">
        <template #default="{ row }">{{ row.lastLoginAt || '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.status === 'ACTIVE'" size="small" type="warning" link
                     :disabled="row.id === auth.user?.id" @click="toggle(row, 'DISABLED')">禁用</el-button>
          <el-button v-else size="small" type="success" link @click="toggle(row, 'ACTIVE')">启用</el-button>
          <el-button size="small" type="primary" link :disabled="!row.loginAccount || row.id === auth.user?.id"
                     @click="openReset(row)">重置密码</el-button>
          <el-button size="small" type="primary" link :disabled="row.id === auth.user?.id"
                     @click="openRole(row)">改角色</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="pager" layout="total, sizes, prev, pager, next, jumper" :total="total"
                   :page-sizes="[10, 20, 50, 100]" :page-size="query.size" :current-page="query.page"
                   @current-change="load" @size-change="onSizeChange" />

    <el-dialog v-model="createVisible" title="新建用户" width="460px" @closed="resetCreate">
      <el-form ref="createRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="登录账号" prop="loginAccount">
          <el-input v-model="createForm.loginAccount" placeholder="比如姓名拼音" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="createForm.name" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="createForm.phone" placeholder="11 位手机号，也可作登录账号" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="选填" />
        </el-form-item>
        <el-form-item label="初始密码" prop="initialPassword">
          <el-input v-model="createForm.initialPassword" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-form-item label="角色" required>
          <div class="role-picker">
            <!-- 嵌套层级卡片：业务角色 ⊃ 需求类型权限（下一级配置）；其他角色在卡片外，不受卡片规则约束 -->
            <ScopedRoleCard v-model:roles="createForm.roles" v-model:types="createForm.types" />
            <div class="role-section other">
              <div class="section-title">其他角色（不受类型权限限制）</div>
              <el-checkbox-group v-model="createForm.roles">
                <el-checkbox v-for="r in otherRoleOptions" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
              </el-checkbox-group>
            </div>
          </div>
        </el-form-item>
        <el-alert type="info" :closable="false" class="role-alert"
                  title="可多选：首个角色为主角色，其余为兼任角色，权限取并集；勾选管理员时将以管理员为主角色" />
        <el-alert type="info" :closable="false" class="role-alert"
                  title="新用户首次登录时会被要求修改初始密码" />
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting"
                   :disabled="!createForm.roles.length || (createHasScopedRole && !createForm.types.length)"
                   @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="roleVisible" :title="`调整角色：${roleTarget?.name}`" width="460px">
      <!-- 嵌套层级卡片：业务角色 ⊃ 需求类型权限（下一级配置）；其他角色在卡片外，不受卡片规则约束 -->
      <ScopedRoleCard v-model:roles="roleForm.roles" v-model:types="roleForm.types" />
      <div class="role-section other">
        <div class="section-title">其他角色（不受类型权限限制）</div>
        <el-checkbox-group v-model="roleForm.roles">
          <el-checkbox v-for="r in otherRoleOptions" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
        </el-checkbox-group>
      </div>
      <el-alert type="info" :closable="false" class="role-alert"
                title="可多选：首个角色为主角色，其余为兼任角色，权限取并集；勾选管理员时将以其为主角色。调整后即时生效，无需重新登录" />
      <template #footer>
        <el-button @click="roleVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting"
                   :disabled="!roleForm.roles.length || (hasScopedRole && !roleForm.types.length)"
                   @click="submitRole">确认调整</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" :title="`重置密码：${resetTarget?.name}`" width="420px">
      <el-form ref="resetRef" :model="resetForm" :rules="resetRules" label-width="90px">
        <el-form-item label="新密码" prop="newPassword">
          <el-input v-model="resetForm.newPassword" type="password" show-password placeholder="至少 8 位" />
        </el-form-item>
        <el-alert type="warning" :closable="false" title="重置后该用户所有登录状态将失效，且首次登录需修改密码" />
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReset">确认重置</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { channelApi, usersApi } from '@/api'
import type { RoleCode, TypeCode, UserRow } from '@/api'
import { ApiError } from '@/api/request'
import ScopedRoleCard, { isScopedRole, typeOptions } from '@/components/ScopedRoleCard.vue'
import { useAuthStore } from '@/stores/auth'

/** P4 五角色：标签/配色统一出处，筛选、新建、改角色共用（REPORTER=渠道默认提报人） */
const roleOptions: { value: RoleCode; label: string; tag: 'danger' | 'warning' | 'primary' | 'info' }[] = [
  { value: 'ADMIN', label: '管理员', tag: 'danger' },
  { value: 'EXECUTIVE', label: '管理者', tag: 'warning' },
  { value: 'MANAGER', label: '经理', tag: 'primary' },
  { value: 'HANDLER', label: '处理人', tag: 'info' },
  { value: 'REPORTER', label: '提报人', tag: 'info' },
]
const roleLabel = (role: RoleCode) => roleOptions.find((r) => r.value === role)?.label ?? role
const roleTagType = (role: RoleCode) => roleOptions.find((r) => r.value === role)?.tag ?? 'info'

/** 其他角色沉底区（提报人/管理员）：在业务角色卡片外，不受类型权限约束（isScopedRole/typeOptions 由 ScopedRoleCard 统一出口） */
const otherRoleOptions = roleOptions.filter((r) => !isScopedRole(r.value))
/** 列表灰字短名：科技 / 物料 / 培训 */
const scopeText = (scope: TypeCode[]) =>
  scope.map((code) => typeOptions.find((t) => t.value === code)?.label.replace('需求', '') ?? code).join(' / ')

const auth = useAuthStore()
const loading = ref(false)
const submitting = ref(false)
const rows = ref<UserRow[]>([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, keyword: '', role: '', status: '' })

/** 每页条数变化：回到第 1 页重新查询，避免"大页码 × 大页容"越界空页 */
function onSizeChange(size: number) {
  query.size = size
  load(1)
}

async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const data = await usersApi.list({
      page: query.page, size: query.size, channel: 'ACCOUNT',  // 只管网内正式用户；渠道用户见「渠道身份」页
      keyword: query.keyword || undefined, role: query.role || undefined, status: query.status || undefined,
    })
    rows.value = data.list
    total.value = data.total
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

async function toggle(row: UserRow, target: 'ACTIVE' | 'DISABLED') {
  try {
    if (target === 'ACTIVE') await usersApi.activate(row.id)
    else await usersApi.disable(row.id)
    ElMessage.success(target === 'ACTIVE' ? '已启用' : '已禁用')
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '操作失败')
  }
}

const createVisible = ref(false)
const createRef = ref<FormInstance>()
/** 新建默认角色：处理人 + 提报人（2026-10-18 拍板：新账号默认兼具提报能力，与渠道建号默认 REPORTER 同口径） */
const createForm = reactive({ loginAccount: '', name: '', phone: '', email: '', initialPassword: '', roles: ['HANDLER', 'REPORTER'] as RoleCode[], types: [] as TypeCode[] })
/** 勾了业务角色才需要（且必须）配类型权限（与改角色同口径） */
const createHasScopedRole = computed(() => createForm.roles.some(isScopedRole))
const createRules: FormRules = {
  loginAccount: [
    { required: true, message: '请输入登录账号', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_.-]{2,64}$/, message: '2-64 位字母/数字/._-（建议姓名拼音）', trigger: 'blur' },
  ],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  phone: [
    { required: true, message: '请输入手机号', trigger: 'blur' },
    { pattern: /^1\d{10}$/, message: '请输入 11 位手机号', trigger: 'blur' },
  ],
  email: [{ pattern: /^[^@\s]+@[^@\s]+\.[^@\s]+$/, message: '邮箱格式不正确', trigger: 'blur' }],
  initialPassword: [
    { required: true, message: '请输入初始密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码长度 8-64 位', trigger: 'blur' },
  ],
}
function resetCreate() {
  Object.assign(createForm, { loginAccount: '', name: '', phone: '', email: '', initialPassword: '', roles: ['HANDLER', 'REPORTER'], types: [] })
}
async function submitCreate() {
  await createRef.value?.validate().catch(() => Promise.reject())
  if (!createForm.roles.length) return  // 按钮已置灰，双保险
  if (createHasScopedRole.value && !createForm.types.length) {
    ElMessage.warning('请为业务角色选择至少一个需求类型权限')
    return
  }
  submitting.value = true
  try {
    await usersApi.create({
      loginAccount: createForm.loginAccount, name: createForm.name,
      phone: createForm.phone, email: createForm.email || undefined,
      initialPassword: createForm.initialPassword, roles: createForm.roles,
      types: createHasScopedRole.value ? createForm.types : undefined,
    })
    ElMessage.success('已创建')
    createVisible.value = false
    await load(1)
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '创建失败')
  } finally {
    submitting.value = false
  }
}

const roleVisible = ref(false)
const roleTarget = ref<UserRow | null>(null)
const roleForm = reactive({ roles: [] as RoleCode[], types: [] as TypeCode[] })
/** 勾了业务角色才需要（且必须）配类型权限 */
const hasScopedRole = computed(() => roleForm.roles.some(isScopedRole))
function openRole(row: UserRow) {
  roleTarget.value = row
  roleForm.roles = [...row.roles]
  roleForm.types = [...(row.typeScope ?? [])]
  roleVisible.value = true
}
async function submitRole() {
  if (!roleTarget.value || !roleForm.roles.length) return
  if (hasScopedRole.value && !roleForm.types.length) return  // 按钮已置灰，双保险
  submitting.value = true
  try {
    await usersApi.updateRoles(roleTarget.value.id, roleForm.roles,
                               hasScopedRole.value ? roleForm.types : undefined)
    ElMessage.success('已调整')
    roleVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '调整失败')
  } finally {
    submitting.value = false
  }
}

const resetVisible = ref(false)
const resetRef = ref<FormInstance>()
const resetTarget = ref<UserRow | null>(null)
const resetForm = reactive({ newPassword: '' })
const resetRules: FormRules = {
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, max: 64, message: '密码长度 8-64 位', trigger: 'blur' },
  ],
}
function openReset(row: UserRow) {
  resetTarget.value = row
  resetForm.newPassword = ''
  resetVisible.value = true
}
async function submitReset() {
  await resetRef.value?.validate().catch(() => Promise.reject())
  if (!resetTarget.value) return
  submitting.value = true
  try {
    await usersApi.resetPassword(resetTarget.value.id, resetForm.newPassword)
    ElMessage.success('已重置')
    resetVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '重置失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => load(1))

// ---- OneID：列表渠道灰字展示（挂接/改挂操作在「渠道身份」页，人归人管、钥匙归钥匙管） ----

/** 渠道代码 → 渠道名映射（列表灰字展示用；加载失败降级显示代码） */
const channelMap = ref<Record<string, string>>({})
const channelLabel = (code: string) => channelMap.value[code] ?? code
channelApi.list()
  .then((channels) => { channelMap.value = Object.fromEntries(channels.map((c) => [c.channelCode, c.channelName])) })
  .catch(() => { /* 渠道名加载失败不阻塞主流程 */ })
</script>

<style scoped>
.toolbar { display: flex; gap: 12px; margin-bottom: 16px; }
.kw { width: 220px; }
.sel { width: 130px; }
.add { margin-left: auto; }
.pager { margin-top: 16px; justify-content: flex-end; }
.role-tag { margin-right: 4px; }
.scope-text { color: #909399; font-size: 12px; margin-top: 4px; }
.role-picker { width: 100%; }
/* 其他角色区：位于业务角色卡片之外，与卡片拉开间距 */
.role-section.other { margin-top: 12px; }
.section-title { font-weight: 600; color: #303133; margin-bottom: 8px; }
.role-alert { margin-top: 12px; }
</style>
