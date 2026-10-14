<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="onCreate">新建类型</el-button>
      <span class="tip">类型编码创建后不可改；状态机 key 未配置时回落内置默认流程（可先绑定后配置）。</span>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="typeCode" label="编码" width="120" />
        <el-table-column prop="typeName" label="名称" min-width="140" />
        <el-table-column prop="defaultOrgId" label="默认承接组织" width="140">
          <template #default="{ row }">{{ orgName(row.defaultOrgId) }}</template>
        </el-table-column>
        <el-table-column prop="stateMachineKey" label="状态机 key" width="150" />
        <el-table-column prop="sort" label="排序" width="80" sortable />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'warning' : 'success'" @click="onToggle(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editVisible" :title="form.id ? '编辑类型' : '新建类型'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="编码">
          <el-input v-model="form.typeCode" :disabled="!!form.id" placeholder="2-16 位大写字母/数字/下划线，如 TECH" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.typeName" placeholder="如 科技需求" />
        </el-form-item>
        <el-form-item label="默认承接组织">
          <el-tree-select v-model="form.defaultOrgId" :data="orgTree" node-key="orgId" check-strictly clearable
                          :props="{ label: 'name', children: 'children' }" :render-after-expand="false"
                          default-expand-all placeholder="留空=管理者队列" style="width: 100%" />
          <div class="form-tip">该类型新提报需求的路由归属；留空则进入管理者队列待分派</div>
        </el-form-item>
        <el-form-item label="状态机 key">
          <el-select v-model="form.stateMachineKey" filterable allow-create default-first-option style="width: 100%">
            <el-option v-for="key in stateMachineKeys" :key="key" :label="key" :value="key" />
          </el-select>
          <div class="form-tip">留 DEFAULT 走内置流程；填新 key 后可到状态机管理配置专属流程</div>
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" :max="9999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { orgApi, stateMachineApi, typeApi } from '@/api'
import type { DemandTypeRow, OrgNode } from '@/api'

const rows = ref<DemandTypeRow[]>([])
const stateMachineKeys = ref<string[]>([])
const orgTree = ref<OrgNode[]>([])
const loading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const form = reactive({
  id: 0, typeCode: '', typeName: '', defaultOrgId: undefined as number | undefined,
  stateMachineKey: 'DEFAULT', sort: 0,
})

async function load() {
  loading.value = true
  try {
    rows.value = await typeApi.list()
  } finally {
    loading.value = false
  }
}

async function loadStateMachineKeys() {
  const machines = await stateMachineApi.list()
  stateMachineKeys.value = ['DEFAULT', ...machines.map(m => m.configKey).filter(k => k !== 'DEFAULT')]
}

async function loadOrgs() {
  orgTree.value = await orgApi.tree().catch(() => [])
}

// 组织 id → 名称（拍平树查找），未配置显示「—」，找不到回退 id
function orgName(id?: number | null) {
  if (id == null) return '—'
  const walk = (nodes: OrgNode[]): OrgNode | undefined => {
    for (const n of nodes) {
      if (n.orgId === id) return n
      const hit = n.children ? walk(n.children) : undefined
      if (hit) return hit
    }
    return undefined
  }
  return walk(orgTree.value)?.name ?? String(id)
}

function onCreate() {
  Object.assign(form, { id: 0, typeCode: '', typeName: '', defaultOrgId: undefined, stateMachineKey: 'DEFAULT', sort: 0 })
  editVisible.value = true
}

function onEdit(row: DemandTypeRow) {
  Object.assign(form, {
    id: row.id, typeCode: row.typeCode, typeName: row.typeName,
    defaultOrgId: row.defaultOrgId ?? undefined, stateMachineKey: row.stateMachineKey, sort: row.sort,
  })
  editVisible.value = true
}

async function onSave() {
  if (!form.typeCode || !form.typeName) {
    ElMessage.error('编码、名称不能为空')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await typeApi.update(form.id, {
        typeName: form.typeName, defaultOrgId: form.defaultOrgId,
        stateMachineKey: form.stateMachineKey, sort: form.sort,
      })
    } else {
      await typeApi.create({
        typeCode: form.typeCode, typeName: form.typeName, defaultOrgId: form.defaultOrgId,
        stateMachineKey: form.stateMachineKey, sort: form.sort,
      })
    }
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onToggle(row: DemandTypeRow) {
  await typeApi.update(row.id, { status: row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' })
  ElMessage.success(row.status === 'ACTIVE' ? '已停用' : '已启用')
  await load()
}

onMounted(() => { load(); loadStateMachineKeys(); loadOrgs() })
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
.form-tip { color: #909399; font-size: 12px; line-height: 1.4; margin-top: 4px; }
</style>
