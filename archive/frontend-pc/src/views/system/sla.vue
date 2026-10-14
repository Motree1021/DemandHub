<template>
  <div class="sla-page">
    <el-card>
      <div class="toolbar">
        <el-select v-model="queryType" placeholder="需求类型（清空查全部）" clearable style="width: 200px" @change="load">
          <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
        </el-select>
        <el-button type="primary" plain @click="openEdit()">新增配置</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column label="需求类型" width="120">
          <template #default="{ row }">{{ typeLabel(row.demandTypeCode) }}</template>
        </el-table-column>
        <el-table-column label="停留状态" min-width="130">
          <template #default="{ row }">{{ statusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="预警阈值" width="110">
          <template #default="{ row }">{{ row.warnMinutes }} 分钟</template>
        </el-table-column>
        <el-table-column label="告警阈值" width="110">
          <template #default="{ row }">{{ row.maxMinutes }} 分钟</template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              :active-value="1"
              :inactive-value="0"
              @change="(val: string | number | boolean) => onToggleEnabled(row, Number(val))"
            />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确认删除该 SLA 配置？" @confirm="onDelete(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑配置' : '新增配置'" width="520px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="需求类型" required>
          <el-select v-model="form.demandTypeCode" :disabled="!!form.id" style="width: 100%">
            <el-option v-for="t in typeOptions" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="停留状态" required>
          <el-select v-model="form.status" :disabled="!!form.id" style="width: 100%">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="预警阈值(分)" required>
          <el-input-number v-model="form.warnMinutes" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="告警阈值(分)" required>
          <el-input-number v-model="form.maxMinutes" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="选填" />
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
import { listSlaConfigs, createSlaConfig, updateSlaConfig, deleteSlaConfig } from '@/api/admin'
import type { SlaConfigItem } from '@/api/admin'
import { statusLabel } from '@/utils/format'

const typeOptions = [
  { label: '科技需求', value: 'TECH' },
  { label: '物料需求', value: 'MATL' },
  { label: '培训需求', value: 'TRAIN' }
]

const statusOptions = [
  { label: '待受理', value: 'SUBMITTED' },
  { label: '待分派/待领取', value: 'TRIAGE' },
  { label: '分析中', value: 'ANALYZING' },
  { label: '方案待评审', value: 'SOLUTION_REVIEW' },
  { label: '已确认/已排期', value: 'CONFIRMED' },
  { label: '处理中', value: 'IN_PROGRESS' },
  { label: '待验收', value: 'ACCEPTANCE' }
]

const queryType = ref('')

const rows = ref<SlaConfigItem[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<Partial<SlaConfigItem>>({})

function typeLabel(code: string) {
  return typeOptions.find((t) => t.value === code)?.label || code
}

async function load() {
  loading.value = true
  try {
    rows.value = await listSlaConfigs(queryType.value || undefined)
  } finally {
    loading.value = false
  }
}

function openEdit(row?: SlaConfigItem) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      demandTypeCode: row.demandTypeCode,
      status: row.status,
      warnMinutes: row.warnMinutes,
      maxMinutes: row.maxMinutes,
      remark: row.remark
    })
  } else {
    Object.assign(form, {
      id: undefined,
      demandTypeCode: queryType.value || 'TECH',
      status: 'SUBMITTED',
      warnMinutes: 30,
      maxMinutes: 60,
      remark: ''
    })
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.demandTypeCode || !form.status) {
    ElMessage.warning('请选择需求类型与停留状态')
    return
  }
  if (!form.warnMinutes || !form.maxMinutes || form.maxMinutes <= form.warnMinutes) {
    ElMessage.error('告警阈值必须大于预警阈值')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await updateSlaConfig(form.id, form)
    } else {
      await createSlaConfig({ ...form, enabled: 1 })
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function onToggleEnabled(row: SlaConfigItem, enabled: number) {
  await updateSlaConfig(row.id, { enabled })
  ElMessage.success(enabled === 1 ? '已启用' : '已停用')
  load()
}

async function onDelete(id: number) {
  await deleteSlaConfig(id)
  ElMessage.success('已删除')
  load()
}

onMounted(() => {
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
