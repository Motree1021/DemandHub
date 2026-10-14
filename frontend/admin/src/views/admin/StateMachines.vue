<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="onCreate">新建配置</el-button>
      <el-button @click="onReload" :loading="reloading">手动重载</el-button>
      <span class="tip">保存后立即生效，无需重启；规则集为整包 JSON，保存时会一次性校验并提示全部错误。</span>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="configKey" label="配置标识" width="160" />
        <el-table-column prop="configName" label="名称" width="160" />
        <el-table-column label="规则数" width="90">
          <template #default="{ row }">{{ ruleCount(row) }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="80" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="updatedAt" label="更新时间" width="170" />
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'warning' : 'success'" @click="onToggle(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editVisible" :title="form.id ? '编辑配置' : '新建配置'" width="720px">
      <el-form label-width="90px">
        <el-form-item label="配置标识">
          <el-input v-model="form.configKey" :disabled="!!form.id" placeholder="如 DEFAULT，类型管理里按此标识绑定" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.configName" placeholder="如 默认流转规则" />
        </el-form-item>
        <el-form-item label="规则集">
          <el-input v-model="form.configJson" type="textarea" :rows="16" class="json-input"
                    placeholder='{"rules": [{"from": "DRAFT", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "提交"}]}' />
        </el-form-item>
        <el-form-item>
          <el-button size="small" @click="onFillDefault">填入默认规则</el-button>
          <span class="tip">默认规则是系统内置兜底，可在其基础上修改。</span>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="可选" />
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
import { stateMachineApi } from '@/api'
import type { StateMachineRow } from '@/api'

const rows = ref<StateMachineRow[]>([])
const loading = ref(false)
const reloading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const form = reactive({ id: 0, configKey: '', configName: '', configJson: '', remark: '' })

function ruleCount(row: StateMachineRow): number | string {
  try {
    const parsed = JSON.parse(row.configJson) as { rules?: unknown[] }
    return parsed.rules?.length ?? '-'
  } catch {
    return '-'
  }
}

async function load() {
  loading.value = true
  try {
    rows.value = await stateMachineApi.list()
  } finally {
    loading.value = false
  }
}

function onCreate() {
  Object.assign(form, { id: 0, configKey: '', configName: '', configJson: '', remark: '' })
  editVisible.value = true
}

function onEdit(row: StateMachineRow) {
  let pretty = row.configJson
  try {
    pretty = JSON.stringify(JSON.parse(row.configJson), null, 2)
  } catch { /* 原样展示 */ }
  Object.assign(form, {
    id: row.id, configKey: row.configKey, configName: row.configName,
    configJson: pretty, remark: row.remark || '',
  })
  editVisible.value = true
}

async function onFillDefault() {
  const { configJson } = await stateMachineApi.defaultJson()
  form.configJson = configJson
  ElMessage.success('已填入默认规则，可在此基础上修改')
}

async function onSave() {
  saving.value = true
  try {
    if (form.id) {
      await stateMachineApi.update(form.id, {
        configName: form.configName, configJson: form.configJson, remark: form.remark || undefined,
      })
    } else {
      await stateMachineApi.create({
        configKey: form.configKey, configName: form.configName,
        configJson: form.configJson, remark: form.remark || undefined,
      })
    }
    ElMessage.success('已保存并生效')
    editVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function onToggle(row: StateMachineRow) {
  await stateMachineApi.update(row.id, { status: row.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' })
  ElMessage.success(row.status === 'ACTIVE' ? '已停用' : '已启用')
  await load()
}

async function onReload() {
  reloading.value = true
  try {
    await stateMachineApi.reload()
    ElMessage.success('已从数据库重新加载全部启用中的规则')
  } finally {
    reloading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
.json-input :deep(textarea) { font-family: Consolas, monospace; font-size: 12px; }
</style>
