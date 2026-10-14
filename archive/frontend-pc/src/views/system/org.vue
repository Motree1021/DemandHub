<template>
  <div class="org-page">
    <el-card>
      <div class="toolbar">
        <el-button type="primary" plain @click="openCreateRoot">新增根级子组织</el-button>
        <el-button @click="loadTree">刷新</el-button>
      </div>
      <div class="org-body">
        <div class="tree-panel">
          <el-tree
            :data="treeData"
            node-key="orgId"
            :props="{ label: 'name', children: 'children' }"
            highlight-current
            default-expand-all
            :expand-on-click-node="false"
            @node-click="onNodeClick"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span>{{ data.name }}</span>
                <el-tag v-if="data.status === 'DISABLED'" type="info" size="small" class="node-tag">停用</el-tag>
                <span v-if="data.externalDeptId" class="ext-id">{{ data.externalDeptId }}</span>
              </span>
            </template>
          </el-tree>
        </div>
        <div class="detail-panel" v-loading="loading">
          <template v-if="selected">
            <el-descriptions :column="1" border class="org-desc">
              <el-descriptions-item label="组织ID">{{ selected.orgId }}</el-descriptions-item>
              <el-descriptions-item label="名称">{{ selected.name }}</el-descriptions-item>
              <el-descriptions-item label="层级">{{ levelLabel(selected.level) }}</el-descriptions-item>
              <el-descriptions-item label="父组织">{{ selected.parentId }}</el-descriptions-item>
              <el-descriptions-item label="路径">{{ selected.path }}</el-descriptions-item>
              <el-descriptions-item label="组织类型">{{ kindLabel(selected.orgKind) }}</el-descriptions-item>
              <el-descriptions-item label="渠道侧部门ID">{{ selected.externalDeptId || '—' }}</el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag :type="selected.status === 'DISABLED' ? 'info' : 'success'">
                  {{ selected.status === 'DISABLED' ? '停用' : '启用' }}
                </el-tag>
              </el-descriptions-item>
            </el-descriptions>
            <div class="detail-actions">
              <el-button type="primary" plain @click="openCreate(selected)">新增子组织</el-button>
              <el-button type="primary" @click="openEdit(selected)">编辑</el-button>
              <el-button type="danger" plain @click="onDelete(selected)">删除</el-button>
            </div>
          </template>
          <el-empty v-else description="请选择左侧组织节点" />
        </div>
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑组织' : '新增组织'" width="520px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="组织名称" />
        </el-form-item>
        <el-form-item label="层级" required>
          <el-select v-model="form.level" style="width: 100%">
            <el-option v-for="l in levelOptions" :key="l.value" :label="l.label" :value="l.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="父组织" required>
          <el-tree-select
            v-model="form.parentId"
            :data="treeData"
            :props="{ label: 'name', value: 'orgId', children: 'children' }"
            check-strictly
            placeholder="选择父组织"
            style="width: 100%"
          />
          <div v-if="form.id" class="tip">编辑时不可选择自身及其子树（由后端校验兜底）</div>
        </el-form-item>
        <el-form-item label="组织类型" required>
          <el-select v-model="form.orgKind" style="width: 100%">
            <el-option v-for="k in kindOptions" :key="k.value" :label="k.label" :value="k.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="渠道侧部门ID">
          <el-input v-model="form.externalDeptId" placeholder="渠道侧部门ID（external_dept_id），可空" />
        </el-form-item>
        <el-form-item v-if="form.id" label="状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="启用" value="ACTIVE" />
            <el-option label="停用" value="DISABLED" />
          </el-select>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { createOrg, updateOrg, deleteOrg, adminOrgTree } from '@/api/system'
import type { OrgSaveRequest, AdminOrgNode } from '@/api/system'

const levelOptions = [
  { label: '业务线', value: 'LINE' },
  { label: '部门', value: 'DEPT' },
  { label: '小组', value: 'GROUP' }
] as const

const kindOptions = [
  { label: '提报组织', value: 'REPORTER' },
  { label: '承接组织', value: 'ASSIGNER' },
  { label: '两者', value: 'BOTH' }
] as const

const treeData = ref<AdminOrgNode[]>([])
const selected = ref<AdminOrgNode | null>(null)
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)

const form = reactive<OrgSaveRequest>({
  name: '',
  level: 'DEPT',
  parentId: 0,
  orgKind: 'BOTH',
  externalDeptId: '',
  status: 'ACTIVE'
})

function levelLabel(level: string) {
  return levelOptions.find((l) => l.value === level)?.label || level
}

function kindLabel(kind: string | null) {
  return kindOptions.find((k) => k.value === kind)?.label || kind || '—'
}

function findNode(nodes: AdminOrgNode[], orgId: number): AdminOrgNode | null {
  for (const n of nodes) {
    if (n.orgId === orgId) return n
    if (n.children) {
      const hit = findNode(n.children, orgId)
      if (hit) return hit
    }
  }
  return null
}

async function loadTree() {
  loading.value = true
  try {
    treeData.value = await adminOrgTree()
    if (selected.value) {
      selected.value = findNode(treeData.value, selected.value.orgId)
    }
  } finally {
    loading.value = false
  }
}

function onNodeClick(data: AdminOrgNode) {
  selected.value = data
}

function resetForm() {
  Object.assign(form, { id: undefined, name: '', level: 'DEPT', parentId: 0, orgKind: 'BOTH', externalDeptId: '', status: 'ACTIVE' })
}

function openCreateRoot() {
  if (!treeData.value.length) {
    ElMessage.warning('组织树为空，无法定位根节点')
    return
  }
  resetForm()
  form.parentId = treeData.value[0].orgId
  dialogVisible.value = true
}

function openCreate(parent: AdminOrgNode) {
  resetForm()
  form.parentId = parent.orgId
  dialogVisible.value = true
}

function openEdit(node: AdminOrgNode) {
  Object.assign(form, {
    id: node.orgId,
    name: node.name,
    level: node.level as OrgSaveRequest['level'],
    parentId: node.parentId,
    orgKind: (node.orgKind as OrgSaveRequest['orgKind']) || 'BOTH',
    externalDeptId: node.externalDeptId || '',
    status: node.status || 'ACTIVE'
  })
  dialogVisible.value = true
}

async function onSave() {
  if (!form.name?.trim()) {
    ElMessage.warning('请填写组织名称')
    return
  }
  if (!form.parentId) {
    ElMessage.warning('请选择父组织')
    return
  }
  saving.value = true
  try {
    const payload: OrgSaveRequest = {
      ...form,
      name: form.name.trim(),
      externalDeptId: form.externalDeptId?.trim() ? form.externalDeptId.trim() : null
    }
    if (form.id) {
      await updateOrg(form.id, payload)
    } else {
      await createOrg(payload)
    }
    ElMessage.success('已保存')
    dialogVisible.value = false
    await loadTree()
  } finally {
    saving.value = false
  }
}

async function onDelete(node: AdminOrgNode) {
  await ElMessageBox.confirm(
    `确认删除组织「${node.name}」？存在子组织/用户/授权/需求引用时将被拒绝`,
    '删除确认',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
  await deleteOrg(node.orgId)
  ElMessage.success('已删除')
  if (selected.value?.orgId === node.orgId) {
    selected.value = null
  }
  await loadTree()
}

onMounted(loadTree)
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.org-body {
  display: flex;
  gap: 24px;
  align-items: flex-start;
}

.tree-panel {
  width: 320px;
  flex-shrink: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  max-height: 640px;
  overflow: auto;
}

.detail-panel {
  flex: 1;
  min-width: 0;
}

.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.node-tag {
  margin-left: 4px;
}

.ext-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.org-desc {
  max-width: 640px;
}

.detail-actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
}

.tip {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
</style>
