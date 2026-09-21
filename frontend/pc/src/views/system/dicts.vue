<template>
  <div class="dicts-page">
    <el-card>
      <div class="toolbar">
        <el-select v-model="currentType" placeholder="选择字典分组" filterable clearable style="width: 220px" @change="load">
          <el-option v-for="t in typeOptions" :key="t" :label="t" :value="t" />
        </el-select>
        <el-button type="primary" plain @click="openEdit()">新增字典项</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="itemCode" label="字典项编码" width="160" />
        <el-table-column prop="itemName" label="名称" min-width="160" />
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

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑字典项' : '新增字典项'" width="520px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="字典分组" required>
          <el-select
            v-model="form.dictType"
            filterable
            allow-create
            default-first-option
            placeholder="选择已有分组或输入新分组"
            style="width: 100%"
          >
            <el-option v-for="t in typeOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="字典项编码" required>
          <el-input v-model="form.itemCode" :disabled="!!form.id" placeholder="如 HIGH" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.itemName" placeholder="如 高" />
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
import { listSysDicts, listSysDictTypes, createSysDict, updateSysDict } from '@/api/admin'
import type { SysDictItem } from '@/api/admin'

const typeOptions = ref<string[]>([])
const currentType = ref('')

const rows = ref<SysDictItem[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<Partial<SysDictItem>>({})

async function loadTypes() {
  typeOptions.value = await listSysDictTypes()
  if (!currentType.value && typeOptions.value.length > 0) {
    currentType.value = typeOptions.value[0]
  }
}

async function load() {
  loading.value = true
  try {
    rows.value = await listSysDicts(currentType.value || undefined)
  } finally {
    loading.value = false
  }
}

function openEdit(row?: SysDictItem) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      dictType: row.dictType,
      itemCode: row.itemCode,
      itemName: row.itemName,
      sort: row.sort,
      status: row.status
    })
  } else {
    Object.assign(form, {
      id: undefined,
      dictType: currentType.value || '',
      itemCode: '',
      itemName: '',
      sort: 0,
      status: 'ACTIVE'
    })
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.dictType || !form.itemCode || !form.itemName) {
    ElMessage.warning('请填写分组、编码与名称')
    return
  }
  const isNewType = !typeOptions.value.includes(form.dictType)
  saving.value = true
  try {
    if (form.id) {
      await updateSysDict(form.id, form)
    } else {
      await createSysDict(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    if (isNewType) {
      await loadTypes()
    }
    if (form.dictType && form.dictType !== currentType.value) {
      currentType.value = form.dictType
    }
    load()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await loadTypes()
  load()
})
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
</style>
