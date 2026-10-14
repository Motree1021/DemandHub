<template>
  <div>
    <div class="toolbar">
      <el-select v-model="dictType" placeholder="全部分组" clearable filterable style="width: 220px" @change="load">
        <el-option v-for="t in types" :key="t" :label="t" :value="t" />
      </el-select>
      <el-button type="primary" @click="onCreate">新建字典项</el-button>
      <span class="tip">字典编码创建后不可改（历史数据按编码关联）；停用后历史数据仍按原名称展示。</span>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="dictType" label="分组" width="160" />
        <el-table-column prop="itemCode" label="编码" width="140" />
        <el-table-column prop="itemName" label="名称" min-width="160" show-overflow-tooltip />
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

    <el-dialog v-model="editVisible" :title="form.id ? '编辑字典项' : '新建字典项'" width="520px">
      <el-form label-width="90px">
        <el-form-item label="分组">
          <el-select v-model="form.dictType" :disabled="!!form.id" filterable allow-create default-first-option
                     placeholder="选择已有分组或输入新分组名" style="width: 100%">
            <el-option v-for="t in types" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="form.itemCode" :disabled="!!form.id" placeholder="如 NORMAL" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.itemName" placeholder="如 普通" />
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
import { dictApi } from '@/api'
import type { SysDictRow } from '@/api'

const rows = ref<SysDictRow[]>([])
const types = ref<string[]>([])
const dictType = ref('')
const loading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const form = reactive({ id: 0, dictType: '', itemCode: '', itemName: '', sort: 0 })

async function load() {
  loading.value = true
  try {
    rows.value = await dictApi.list(dictType.value || undefined)
  } finally {
    loading.value = false
  }
}

async function loadTypes() {
  types.value = await dictApi.types()
}

function onCreate() {
  Object.assign(form, { id: 0, dictType: dictType.value, itemCode: '', itemName: '', sort: 0 })
  editVisible.value = true
}

function onEdit(row: SysDictRow) {
  Object.assign(form, { id: row.id, dictType: row.dictType, itemCode: row.itemCode, itemName: row.itemName, sort: row.sort })
  editVisible.value = true
}

async function onSave() {
  if (!form.dictType || !form.itemCode || !form.itemName) {
    ElMessage.error('分组、编码、名称不能为空')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await dictApi.update(form.id, { itemName: form.itemName, sort: form.sort })
    } else {
      await dictApi.create({ dictType: form.dictType, itemCode: form.itemCode, itemName: form.itemName, sort: form.sort })
    }
    ElMessage.success('已保存')
    editVisible.value = false
    await Promise.all([load(), loadTypes()])
  } catch (error) {
    ElMessage.error((error as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onToggle(row: SysDictRow) {
  await dictApi.update(row.id, { status: row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' })
  ElMessage.success(row.status === 'ACTIVE' ? '已停用' : '已启用')
  await load()
}

onMounted(() => { load(); loadTypes() })
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
</style>
