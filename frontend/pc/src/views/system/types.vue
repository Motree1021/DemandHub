<template>
  <div class="types-page">
    <el-card>
      <div class="toolbar">
        <el-button type="primary" plain @click="openEdit()">新增类型</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="typeCode" label="类型编码" width="120" />
        <el-table-column prop="typeName" label="名称" min-width="140" />
        <el-table-column label="默认承接组织" min-width="160">
          <template #default="{ row }">{{ row.defaultOrgId == null ? '-' : orgName(row.defaultOrgId) }}</template>
        </el-table-column>
        <el-table-column label="状态机" width="140">
          <template #default="{ row }">{{ row.stateMachineKey || '-' }}</template>
        </el-table-column>
        <el-table-column prop="sort" label="排序" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑类型' : '新增类型'" width="520px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="类型编码" required>
          <el-input v-model="form.typeCode" :disabled="!!form.id" placeholder="如 TECH" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.typeName" placeholder="如 科技需求" />
        </el-form-item>
        <el-form-item label="默认承接组织">
          <el-select v-model="form.defaultOrgId" clearable placeholder="不选表示无默认组织" style="width: 100%">
            <el-option v-for="o in orgOptions" :key="o.orgId" :label="o.name" :value="o.orgId" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态机">
          <el-input v-model="form.stateMachineKey" placeholder="默认 DEFAULT" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" active-value="ACTIVE" inactive-value="DISABLED" active-text="启用" inactive-text="停用" />
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
import { listDemandTypes, createDemandType, updateDemandType } from '@/api/admin'
import type { DemandTypeItem } from '@/api/admin'
import { listOrgs } from '@/api/directory'
import type { OrgFlat } from '@/api/directory'

const rows = ref<DemandTypeItem[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<Partial<DemandTypeItem>>({})

const orgOptions = ref<OrgFlat[]>([])
const orgNameMap = ref<Record<number, string>>({})

function orgName(orgId: number) {
  return orgNameMap.value[orgId] || String(orgId)
}

async function load() {
  loading.value = true
  try {
    rows.value = await listDemandTypes()
  } finally {
    loading.value = false
  }
}

function openEdit(row?: DemandTypeItem) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      typeCode: row.typeCode,
      typeName: row.typeName,
      defaultOrgId: row.defaultOrgId,
      stateMachineKey: row.stateMachineKey || 'DEFAULT',
      sort: row.sort,
      status: row.status
    })
  } else {
    Object.assign(form, {
      id: undefined,
      typeCode: '',
      typeName: '',
      defaultOrgId: null,
      stateMachineKey: 'DEFAULT',
      sort: 0,
      status: 'ACTIVE'
    })
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.typeCode || !form.typeName) {
    ElMessage.warning('请填写类型编码与名称')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await updateDemandType(form.id, form)
    } else {
      await createDemandType(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  load()
  const orgs = await listOrgs()
  orgOptions.value = orgs
  orgs.forEach((o) => {
    orgNameMap.value[o.orgId] = o.name
  })
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
