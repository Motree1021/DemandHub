<template>
  <div>
    <div class="bar">
      <el-statistic title="累计工时（小时）" :value="summary?.totalHours ?? 0" class="stat" />
      <div class="by-user">
        <el-tag v-for="u in summary?.byUser || []" :key="u.userId" size="small" class="u-tag">
          {{ u.userName }}：{{ u.hours }}h
        </el-tag>
      </div>
      <el-button v-if="canAdd" type="primary" size="small" @click="openEdit(null)">填报工时</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="workDate" label="日期" width="120" />
      <el-table-column prop="userName" label="填报人" width="110" />
      <el-table-column prop="hours" label="工时(h)" width="90" />
      <el-table-column prop="remark" label="工作内容" min-width="240">
        <template #default="{ row }">{{ row.remark || '—' }}</template>
      </el-table-column>
      <el-table-column prop="createdAt" label="填报时间" width="165" />
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button v-if="row.userId === auth.user?.id" size="small" link type="primary"
                     @click="openEdit(row)">编辑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="editVisible" :title="editRow ? '编辑工时' : '填报工时'" width="440px">
      <el-form label-width="90px">
        <el-form-item label="工作日期" required>
          <el-date-picker v-model="form.workDate" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="工时(h)" required>
          <el-input-number v-model="form.hours" :min="0.5" :max="24" :step="0.5" />
        </el-form-item>
        <el-form-item label="工作内容">
          <el-input v-model="form.remark" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { effortApi } from '@/api'
import type { DemandRow, EffortRow, EffortSummary } from '@/api'
import { ApiError } from '@/api/request'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ demand: DemandRow }>()
const auth = useAuthStore()

const loading = ref(false)
const submitting = ref(false)
const rows = ref<EffortRow[]>([])
const summary = ref<EffortSummary | null>(null)

/** 终态（已完成/已关闭）不可再填报，后端同样强校验 */
const canAdd = computed(() => !['DONE', 'CLOSED'].includes(props.demand.status))

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function load() {
  loading.value = true
  try {
    const [list, sum] = await Promise.all([effortApi.list(props.demand.id), effortApi.summary(props.demand.id)])
    rows.value = list
    summary.value = sum
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

const editVisible = ref(false)
const editRow = ref<EffortRow | null>(null)
const form = reactive({ workDate: '', hours: 1, remark: '' })

function openEdit(row: EffortRow | null) {
  editRow.value = row
  form.workDate = row?.workDate || new Date().toISOString().slice(0, 10)
  form.hours = row?.hours ?? 1
  form.remark = row?.remark || ''
  editVisible.value = true
}

async function saveEdit() {
  if (!form.workDate) {
    ElMessage.warning('请选择工作日期')
    return
  }
  submitting.value = true
  try {
    const payload = { workDate: form.workDate, hours: form.hours, remark: form.remark || undefined }
    if (editRow.value) {
      await effortApi.update(editRow.value.id, payload)
    } else {
      await effortApi.add({ demandId: props.demand.id, ...payload })
    }
    ElMessage.success('已保存')
    editVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, '保存失败'))
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.bar { display: flex; align-items: center; gap: 24px; margin-bottom: 16px; }
.stat { flex-shrink: 0; }
.by-user { display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }
</style>
