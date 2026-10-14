<template>
  <div>
    <div class="bar">
      <el-button type="primary" size="small" @click="addVisible = true">添加关联</el-button>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="关系" width="110">
        <template #default="{ row }">{{ RELATION_TYPE_META[row.type] || row.type }}</template>
      </el-table-column>
      <el-table-column label="方向" width="130">
        <template #default="{ row }">{{ row.direction === 'OUT' ? '本需求 → 对方' : '对方 → 本需求' }}</template>
      </el-table-column>
      <el-table-column label="对方需求" min-width="320">
        <template #default="{ row }">
          <el-link type="primary" @click="goOther(row)">
            {{ row.otherDemandNo || `#${row.otherDemandId}` }} {{ row.otherTitle || '' }}
          </el-link>
        </template>
      </el-table-column>
      <el-table-column label="对方状态" width="120">
        <template #default="{ row }">
          <StatusTag v-if="row.otherStatus" :status="row.otherStatus" :on-hold="false" :hold-reason="null" />
        </template>
      </el-table-column>
      <el-table-column prop="createdAt" label="建立时间" width="165" />
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="danger" @click="remove(row)">解除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addVisible" title="添加关联" width="440px">
      <el-form label-width="90px">
        <el-form-item label="对方需求" required>
          <el-input-number v-model="addForm.relatedDemandId" :min="1" :controls="false" placeholder="输入对方需求 ID"
                           class="id-input" />
          <div class="tip">暂按 ID 关联（列表页可复制 ID）</div>
        </el-form-item>
        <el-form-item label="关系类型" required>
          <el-select v-model="addForm.relationType">
            <el-option v-for="(label, k) in RELATION_TYPE_META" :key="k" :label="label" :value="k" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!addForm.relatedDemandId" @click="saveAdd">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { relationApi } from '@/api'
import type { RelationRow } from '@/api'
import { ApiError } from '@/api/request'
import { RELATION_TYPE_META } from '@/utils/status'
import StatusTag from '@/components/StatusTag.vue'

const props = defineProps<{ demandId: number }>()
const router = useRouter()

const loading = ref(false)
const submitting = ref(false)
const rows = ref<RelationRow[]>([])

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function load() {
  loading.value = true
  try {
    rows.value = await relationApi.list(props.demandId)
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const addVisible = ref(false)
const addForm = reactive({ relatedDemandId: undefined as number | undefined, relationType: 'PARENT' })

async function saveAdd() {
  if (!addForm.relatedDemandId) return
  submitting.value = true
  try {
    await relationApi.add(props.demandId, addForm.relatedDemandId, addForm.relationType)
    ElMessage.success('已添加')
    addVisible.value = false
    addForm.relatedDemandId = undefined
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, '添加失败'))
  } finally {
    submitting.value = false
  }
}

async function remove(row: RelationRow) {
  try {
    await ElMessageBox.confirm(`解除与 ${row.otherDemandNo || row.otherDemandId} 的关联？`, '解除关联',
      { type: 'warning', confirmButtonText: '解除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await relationApi.remove(row.id)
    ElMessage.success('已解除')
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, '解除失败'))
  }
}

function goOther(row: RelationRow) {
  router.push(`/demands/${row.otherDemandId}`)
}

onMounted(load)
</script>

<style scoped>
.bar { display: flex; gap: 8px; margin-bottom: 12px; }
.id-input { width: 200px; }
.tip { color: #909399; font-size: 12px; margin-top: 4px; }
</style>
