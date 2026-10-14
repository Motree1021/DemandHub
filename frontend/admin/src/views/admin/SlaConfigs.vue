<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="onCreate">新建配置</el-button>
      <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 180px" @change="load">
        <el-option v-for="t in typeOptions" :key="t.typeCode" :label="`${t.typeName}（${t.typeCode}）`" :value="t.typeCode" />
      </el-select>
      <span class="tip">需求在某状态停留超过「预警」发黄牌提醒，超过「告警」发红牌催办；挂起中的需求不告警。</span>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="demandTypeCode" label="类型" width="110" />
        <el-table-column label="状态" width="140">
          <template #default="{ row }">{{ statusLabel(row.status) }}</template>
        </el-table-column>
        <el-table-column label="预警（分钟）" width="110" prop="warnMinutes" sortable />
        <el-table-column label="告警（分钟）" width="110" prop="maxMinutes" sortable />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
            <el-button link :type="row.enabled ? 'warning' : 'success'" @click="onToggle(row)">
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editVisible" :title="form.id ? '编辑配置' : '新建配置'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="需求类型">
          <el-select v-model="form.demandTypeCode" :disabled="!!form.id" placeholder="选择类型" style="width: 100%">
            <el-option v-for="t in typeOptions" :key="t.typeCode" :label="`${t.typeName}（${t.typeCode}）`" :value="t.typeCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" :disabled="!!form.id" placeholder="选择状态" style="width: 100%">
            <el-option v-for="(label, value) in STATUS_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="预警（分钟）">
          <el-input-number v-model="form.warnMinutes" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="告警（分钟）">
          <el-input-number v-model="form.maxMinutes" :min="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="如 受理时限：1天预警 / 2天告警（可选）" />
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { slaApi, typeApi } from '@/api'
import type { DemandTypeRow, SlaConfigRow } from '@/api'

// 主状态（与后端一致；ON_HOLD 挂起是叠加态，不参与 SLA 配置）
const STATUS_LABELS: Record<string, string> = {
  DRAFT: '草稿', SUBMITTED: '待受理', NEED_INFO: '待补充', TRIAGE: '待分派/待领取',
  ANALYZING: '分析中', SOLUTION_REVIEW: '方案待评审', CONFIRMED: '已确认/已排期',
  IN_PROGRESS: '处理中', ACCEPTANCE: '待验收', DONE: '已完成', CLOSED: '已关闭',
}

const rows = ref<SlaConfigRow[]>([])
const typeOptions = ref<DemandTypeRow[]>([])
const filterType = ref<string>()
const loading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const form = reactive({
  id: 0, demandTypeCode: '', status: '', warnMinutes: 1440, maxMinutes: 2880, remark: '',
})

function statusLabel(status: string): string {
  return STATUS_LABELS[status] ? `${STATUS_LABELS[status]}（${status}）` : status
}

async function load() {
  loading.value = true
  try {
    rows.value = await slaApi.list(filterType.value || undefined)
  } finally {
    loading.value = false
  }
}

function onCreate() {
  Object.assign(form, { id: 0, demandTypeCode: '', status: '', warnMinutes: 1440, maxMinutes: 2880, remark: '' })
  editVisible.value = true
}

function onEdit(row: SlaConfigRow) {
  Object.assign(form, {
    id: row.id, demandTypeCode: row.demandTypeCode, status: row.status,
    warnMinutes: row.warnMinutes, maxMinutes: row.maxMinutes, remark: row.remark || '',
  })
  editVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    if (form.id) {
      await slaApi.update(form.id, {
        warnMinutes: form.warnMinutes, maxMinutes: form.maxMinutes, remark: form.remark || undefined,
      })
    } else {
      await slaApi.create({
        demandTypeCode: form.demandTypeCode, status: form.status,
        warnMinutes: form.warnMinutes, maxMinutes: form.maxMinutes, remark: form.remark || undefined,
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

async function onToggle(row: SlaConfigRow) {
  await slaApi.update(row.id, { enabled: !row.enabled })
  ElMessage.success(row.enabled ? '已停用' : '已启用')
  await load()
}

async function onRemove(row: SlaConfigRow) {
  await ElMessageBox.confirm(
    `确认删除「${row.demandTypeCode} / ${STATUS_LABELS[row.status] || row.status}」的 SLA 配置？删除后该组合不再告警。`,
    '删除确认', { type: 'warning' })
  await slaApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(async () => {
  typeOptions.value = await typeApi.list()
  await load()
})
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
</style>
