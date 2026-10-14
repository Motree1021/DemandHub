<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="onCreate">新建模板</el-button>
      <span class="tip">模板编码与通知事件一一对应；${变量} 会在发送时替换为实际值，未提供的变量替换为空。</span>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" v-loading="loading">
        <el-table-column prop="templateCode" label="编码" width="180" />
        <el-table-column prop="templateName" label="名称" width="160" />
        <el-table-column prop="titleTemplate" label="标题模板" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="onEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="onPreview(row)">预览</el-button>
            <el-button link :type="row.status === 'ACTIVE' ? 'warning' : 'success'" @click="onToggle(row)">
              {{ row.status === 'ACTIVE' ? '停用' : '启用' }}
            </el-button>
            <el-button link type="danger" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editVisible" :title="form.id ? '编辑模板' : '新建模板'" width="560px">
      <el-form label-width="90px">
        <el-form-item label="编码">
          <el-input v-model="form.templateCode" :disabled="!!form.id" placeholder="如 SLA_ALERT" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.templateName" placeholder="如 SLA 告警" />
        </el-form-item>
        <el-form-item label="标题模板">
          <el-input v-model="form.titleTemplate" placeholder="SLA${level_text}：${demand_no}" />
        </el-form-item>
        <el-form-item label="内容模板">
          <el-input v-model="form.contentTemplate" type="textarea" :rows="4"
                    placeholder="需求${demand_no}「${title}」在状态「${to_status}」已停留${elapsed_minutes}分钟" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="可用变量说明等（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="模板预览" width="560px">
      <el-form label-width="90px">
        <el-form-item label="变量">
          <el-input v-model="previewVars" type="textarea" :rows="4"
                    placeholder='JSON，如 {"demand_no": "D20261014-001", "title": "夹具需求"}' />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="previewing" @click="onRunPreview">渲染预览</el-button>
        </el-form-item>
        <template v-if="previewResult">
          <el-form-item label="标题">
            <div class="preview-box">{{ previewResult.title }}</div>
          </el-form-item>
          <el-form-item label="内容">
            <div class="preview-box">{{ previewResult.content }}</div>
          </el-form-item>
        </template>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { notifyTemplateApi } from '@/api'
import type { NotifyTemplateRow } from '@/api'

const rows = ref<NotifyTemplateRow[]>([])
const loading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const form = reactive({
  id: 0, templateCode: '', templateName: '', titleTemplate: '', contentTemplate: '', remark: '',
})
const previewVisible = ref(false)
const previewing = ref(false)
const previewRow = ref<NotifyTemplateRow>()
const previewVars = ref('{\n  "demand_no": "D20261014-001",\n  "title": "示例需求"\n}')
const previewResult = ref<{ title: string; content: string }>()

async function load() {
  loading.value = true
  try {
    rows.value = await notifyTemplateApi.list()
  } finally {
    loading.value = false
  }
}

function onCreate() {
  Object.assign(form, { id: 0, templateCode: '', templateName: '', titleTemplate: '', contentTemplate: '', remark: '' })
  editVisible.value = true
}

function onEdit(row: NotifyTemplateRow) {
  Object.assign(form, {
    id: row.id, templateCode: row.templateCode, templateName: row.templateName,
    titleTemplate: row.titleTemplate, contentTemplate: row.contentTemplate, remark: row.remark || '',
  })
  editVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    if (form.id) {
      await notifyTemplateApi.update(form.id, {
        templateName: form.templateName, titleTemplate: form.titleTemplate,
        contentTemplate: form.contentTemplate, remark: form.remark || undefined,
      })
    } else {
      await notifyTemplateApi.create({
        templateCode: form.templateCode, templateName: form.templateName,
        titleTemplate: form.titleTemplate, contentTemplate: form.contentTemplate,
        remark: form.remark || undefined,
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

async function onToggle(row: NotifyTemplateRow) {
  await notifyTemplateApi.update(row.id, { status: row.status === 'ACTIVE' ? 'INACTIVE' : 'ACTIVE' })
  ElMessage.success(row.status === 'ACTIVE' ? '已停用' : '已启用')
  await load()
}

async function onRemove(row: NotifyTemplateRow) {
  await ElMessageBox.confirm(`确认删除模板「${row.templateName}」？删除后对应事件将不再发送通知。`,
    '删除确认', { type: 'warning' })
  await notifyTemplateApi.remove(row.id)
  ElMessage.success('已删除')
  await load()
}

function onPreview(row: NotifyTemplateRow) {
  previewRow.value = row
  previewResult.value = undefined
  previewVisible.value = true
}

async function onRunPreview() {
  let variables: Record<string, unknown>
  try {
    variables = JSON.parse(previewVars.value || '{}')
  } catch {
    ElMessage.error('变量不是合法 JSON')
    return
  }
  previewing.value = true
  try {
    previewResult.value = await notifyTemplateApi.preview({
      templateCode: previewRow.value?.templateCode, variables,
    })
  } catch (error) {
    ElMessage.error((error as Error).message || '预览失败')
  } finally {
    previewing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
.preview-box { background: #f5f7fa; border-radius: 4px; padding: 8px 12px; width: 100%; white-space: pre-wrap; }
</style>
