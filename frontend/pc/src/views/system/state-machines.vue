<template>
  <div class="state-machines-page">
    <el-card>
      <div class="toolbar">
        <el-button type="primary" plain @click="openEdit()">新增配置</el-button>
        <el-button @click="openDefaultJson">导出默认模板</el-button>
        <el-button type="warning" plain :loading="reloading" @click="onReload">手动热加载</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="configKey" label="配置标识" width="140" />
        <el-table-column prop="configName" label="名称" min-width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.updatedAt) }}</template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">{{ row.remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑配置' : '新增配置'" width="760px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="配置标识" required>
          <el-input v-model="form.configKey" :disabled="!!form.id" placeholder="如 DEFAULT" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.configName" placeholder="如 默认状态机" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" active-value="ACTIVE" inactive-value="DISABLED" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="选填" />
        </el-form-item>
        <el-form-item label="规则 JSON" required>
          <el-input
            v-model="form.configJson"
            type="textarea"
            :rows="16"
            style="font-family: monospace"
            placeholder='{"rules":[...]}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="defaultJsonVisible" title="默认状态机模板" width="640px">
      <el-input v-model="defaultJson" type="textarea" :rows="16" readonly style="font-family: monospace" />
      <template #footer>
        <el-button @click="defaultJsonVisible = false">关闭</el-button>
        <el-button type="primary" @click="onCopyDefault">复制</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listStateMachines,
  getStateMachineDefaultJson,
  createStateMachine,
  updateStateMachine,
  reloadStateMachines
} from '@/api/admin'
import type { StateMachineConfigItem } from '@/api/admin'
import { fmtTime } from '@/utils/format'

const EXAMPLE_JSON = '{"rules":[{"from":"SUBMITTED","event":"ACCEPT","to":"TRIAGE","roles":["DEMAND_MANAGER"],"remark":"示例"}]}'

const rows = ref<StateMachineConfigItem[]>([])
const loading = ref(false)
const reloading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<Partial<StateMachineConfigItem>>({})

const defaultJsonVisible = ref(false)
const defaultJson = ref('')

async function load() {
  loading.value = true
  try {
    rows.value = await listStateMachines()
  } finally {
    loading.value = false
  }
}

function openEdit(row?: StateMachineConfigItem) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      configKey: row.configKey,
      configName: row.configName,
      status: row.status,
      remark: row.remark,
      configJson: row.configJson
    })
  } else {
    Object.assign(form, {
      id: undefined,
      configKey: '',
      configName: '',
      status: 'ACTIVE',
      remark: '',
      configJson: EXAMPLE_JSON
    })
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.configKey || !form.configName) {
    ElMessage.warning('请填写配置标识与名称')
    return
  }
  try {
    JSON.parse(form.configJson || '')
  } catch {
    ElMessage.error('JSON 格式不合法')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await updateStateMachine(form.id, form)
    } else {
      await createStateMachine(form)
    }
    ElMessage.success('保存成功，已热生效')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

async function openDefaultJson() {
  const data = await getStateMachineDefaultJson()
  defaultJson.value = data.configJson
  defaultJsonVisible.value = true
}

async function onCopyDefault() {
  try {
    await navigator.clipboard.writeText(defaultJson.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

async function onReload() {
  reloading.value = true
  try {
    await reloadStateMachines()
    ElMessage.success('已热加载生效')
  } finally {
    reloading.value = false
  }
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
