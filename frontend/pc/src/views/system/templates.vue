<template>
  <div class="templates-page">
    <el-card>
      <div class="toolbar">
        <el-button type="primary" plain @click="openEdit()">新增模板</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="templateCode" label="模板编码" width="180" />
        <el-table-column prop="templateName" label="名称" min-width="140" />
        <el-table-column prop="titleTemplate" label="标题模板" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="openPreview(row)">预览</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑模板' : '新增模板'" width="640px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="模板编码" required>
          <el-input v-model="form.templateCode" :disabled="!!form.id" placeholder="如 DEMAND_SUBMITTED" />
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.templateName" placeholder="如 需求提交通知" />
        </el-form-item>
        <el-form-item label="标题模板" required>
          <el-input v-model="form.titleTemplate" placeholder="如 新需求待受理：${title}" />
        </el-form-item>
        <el-form-item label="内容模板" required>
          <el-input v-model="form.contentTemplate" type="textarea" :rows="6" placeholder="支持 ${var} 占位符" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.status" active-value="ACTIVE" inactive-value="DISABLED" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" placeholder="选填" />
        </el-form-item>
      </el-form>
      <div class="var-tip">
        可用变量：${demand_no} ${title} ${operator_name} ${from_status} ${to_status} ${comment} ${link} ${level_text} ${elapsed_minutes}
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="previewVisible" title="模板预览" width="640px">
      <el-form label-width="110px">
        <el-form-item label="模板编码">
          <el-input v-model="previewCode" disabled />
        </el-form-item>
        <el-form-item label="变量 JSON">
          <el-input v-model="previewVars" type="textarea" :rows="6" style="font-family: monospace" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="previewing" @click="onPreview">渲染</el-button>
        </el-form-item>
      </el-form>
      <el-descriptions v-if="previewResult" :column="1" border>
        <el-descriptions-item label="标题">{{ previewResult.title }}</el-descriptions-item>
        <el-descriptions-item label="内容">
          <div class="preview-content">{{ previewResult.content }}</div>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listTemplates, createTemplate, updateTemplate, previewTemplate } from '@/api/notification'
import type { TemplateItem } from '@/api/notification'

const EXAMPLE_VARS = '{"demand_no":"TECH-20260921-001","title":"示例需求","operator_name":"张三","comment":"请补充说明"}'

const rows = ref<TemplateItem[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const saving = ref(false)
const form = reactive<Partial<TemplateItem>>({})

const previewVisible = ref(false)
const previewing = ref(false)
const previewCode = ref('')
const previewVars = ref(EXAMPLE_VARS)
const previewResult = ref<{ title: string; content: string } | null>(null)

async function load() {
  loading.value = true
  try {
    rows.value = await listTemplates()
  } finally {
    loading.value = false
  }
}

function openEdit(row?: TemplateItem) {
  if (row) {
    Object.assign(form, {
      id: row.id,
      templateCode: row.templateCode,
      templateName: row.templateName,
      titleTemplate: row.titleTemplate,
      contentTemplate: row.contentTemplate,
      status: row.status,
      remark: row.remark
    })
  } else {
    Object.assign(form, {
      id: undefined,
      templateCode: '',
      templateName: '',
      titleTemplate: '',
      contentTemplate: '',
      status: 'ACTIVE',
      remark: ''
    })
  }
  dialogVisible.value = true
}

async function onSave() {
  if (!form.templateCode || !form.templateName || !form.titleTemplate || !form.contentTemplate) {
    ElMessage.warning('请填写完整模板信息')
    return
  }
  saving.value = true
  try {
    if (form.id) {
      await updateTemplate(form.id, form)
    } else {
      await createTemplate(form)
    }
    ElMessage.success('保存成功')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}

function openPreview(row: TemplateItem) {
  previewCode.value = row.templateCode
  previewVars.value = EXAMPLE_VARS
  previewResult.value = null
  previewVisible.value = true
}

async function onPreview() {
  let vars: Record<string, unknown>
  try {
    vars = JSON.parse(previewVars.value || '{}')
  } catch {
    ElMessage.error('变量 JSON 格式不合法')
    return
  }
  previewing.value = true
  try {
    previewResult.value = await previewTemplate(previewCode.value, vars)
  } finally {
    previewing.value = false
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

.var-tip {
  padding: 8px 12px;
  margin: 0 0 8px 110px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-radius: 4px;
}

.preview-content {
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
