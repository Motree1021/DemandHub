<template>
  <div>
    <div class="toolbar">
      <span class="tip">组织树用于需求归属与类型路由；根组织与 900 未映射虚拟组织为系统内置，不可删除。新增子组织请在对应节点操作。</span>
    </div>

    <el-card shadow="never">
      <el-tree :data="tree" v-loading="loading" node-key="orgId" default-expand-all :expand-on-click-node="false">
        <template #default="{ data }">
          <div class="node">
            <span class="name" :class="{ disabled: data.status === 'DISABLED' }">
              {{ data.name }}
              <el-tag v-if="data.orgId === 900" size="small" type="warning">虚拟</el-tag>
            </span>
            <el-tag size="small" effect="plain">{{ LEVEL_LABELS[data.level] || data.level }}</el-tag>
            <el-tag v-if="data.orgKind" size="small" effect="plain" type="info">{{ KIND_LABELS[data.orgKind] || data.orgKind }}</el-tag>
            <span v-if="data.externalDeptId" class="ext">企微部门 {{ data.externalDeptId }}</span>
            <el-tag v-if="data.status === 'DISABLED'" size="small" type="info">已停用</el-tag>
            <span class="ops">
              <el-button link type="primary" @click.stop="onCreateChild(data)">新增子组织</el-button>
              <el-button link type="primary" @click.stop="onEdit(data)">编辑</el-button>
              <el-button link :type="data.status === 'ACTIVE' ? 'warning' : 'success'" @click.stop="onToggle(data)">
                {{ data.status === 'ACTIVE' ? '停用' : '启用' }}
              </el-button>
              <el-button link type="danger" @click.stop="onDelete(data)">删除</el-button>
            </span>
          </div>
        </template>
      </el-tree>
    </el-card>

    <el-dialog v-model="editVisible" :title="form.orgId ? '编辑组织' : '新增子组织'" width="520px">
      <el-form label-width="110px">
        <el-form-item label="上级组织">
          <el-tree-select v-model="form.parentId" :data="parentOptions" node-key="orgId" check-strictly
                          :props="{ label: 'name', children: 'children', disabled: 'disabled' }"
                          :render-after-expand="false" default-expand-all style="width: 100%" :disabled="!form.orgId" />
          <div class="form-tip">编辑时更换上级即移动整个子树；不能移动到自身子树下</div>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="如 科技产品一组" />
        </el-form-item>
        <el-form-item label="层级">
          <el-select v-model="form.level" style="width: 100%">
            <el-option v-for="(label, value) in LEVEL_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
          <div class="form-tip">条线 &gt; 部门 &gt; 小组</div>
        </el-form-item>
        <el-form-item label="组织性质">
          <el-select v-model="form.orgKind" style="width: 100%">
            <el-option v-for="(label, value) in KIND_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
          <div class="form-tip">承接方可被类型设为默认承接组织；提报方用于提报人归属</div>
        </el-form-item>
        <el-form-item label="企微部门 ID">
          <el-input v-model="form.externalDeptId" placeholder="渠道回源部门 id，用于提报人组织映射；留空表示不映射" clearable />
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
import { computed, onMounted, reactive, ref } from 'vue'
import { orgApi } from '@/api'
import type { OrgNode } from '@/api'

const LEVEL_LABELS: Record<string, string> = { LINE: '条线', DEPT: '部门', GROUP: '小组' }
const KIND_LABELS: Record<string, string> = { REPORTER: '提报方', ASSIGNER: '承接方', BOTH: '提报+承接' }
// 新增子组织时按父级推导默认层级
const NEXT_LEVEL: Record<string, string> = { LINE: 'DEPT', DEPT: 'GROUP', GROUP: 'GROUP' }

const tree = ref<OrgNode[]>([])
const loading = ref(false)
const editVisible = ref(false)
const saving = ref(false)
const form = reactive({
  orgId: 0, parentId: 0, selfPath: '', name: '', level: 'DEPT', orgKind: 'BOTH', externalDeptId: '',
})

async function load() {
  loading.value = true
  try {
    tree.value = await orgApi.tree()
  } finally {
    loading.value = false
  }
}

// 编辑（移动）时禁用自身子树，防止把父级选到自己下面形成环
function markDisabled(nodes: OrgNode[]): OrgNode[] {
  return nodes.map(n => {
    const banned = form.orgId > 0 && n.path.startsWith(form.selfPath)
    return { ...n, disabled: banned, children: n.children ? markDisabled(n.children) : [] } as OrgNode & { disabled: boolean }
  })
}
const parentOptions = computed(() => (form.orgId ? markDisabled(tree.value) : tree.value))

function onCreateChild(parent: OrgNode) {
  Object.assign(form, {
    orgId: 0, parentId: parent.orgId, selfPath: '', name: '',
    level: NEXT_LEVEL[parent.level] || 'GROUP', orgKind: 'BOTH', externalDeptId: '',
  })
  editVisible.value = true
}

function onEdit(node: OrgNode) {
  Object.assign(form, {
    orgId: node.orgId, parentId: node.parentId, selfPath: node.path, name: node.name,
    level: node.level, orgKind: node.orgKind || 'BOTH', externalDeptId: node.externalDeptId || '',
  })
  editVisible.value = true
}

async function onSave() {
  if (!form.name) {
    ElMessage.error('名称不能为空')
    return
  }
  saving.value = true
  try {
    if (form.orgId) {
      await orgApi.update(form.orgId, {
        parentId: form.parentId, name: form.name, level: form.level,
        orgKind: form.orgKind, externalDeptId: form.externalDeptId || null,
      })
    } else {
      await orgApi.create({
        parentId: form.parentId, name: form.name, level: form.level,
        orgKind: form.orgKind, externalDeptId: form.externalDeptId || undefined,
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

async function onToggle(node: OrgNode) {
  await orgApi.update(node.orgId, { status: node.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE' })
  ElMessage.success(node.status === 'ACTIVE' ? '已停用' : '已启用')
  await load()
}

async function onDelete(node: OrgNode) {
  try {
    await ElMessageBox.confirm(
      `确认删除组织「${node.name}」？存在子组织、授权或需求引用时将被拒绝。`, '删除确认', { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await orgApi.remove(node.orgId)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error((error as Error).message || '删除失败')
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.tip { color: #909399; font-size: 13px; }
.node { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.node .name { font-size: 14px; }
.node .name.disabled { color: #909399; }
.ext { color: #909399; font-size: 12px; }
.ops { margin-left: auto; }
.form-tip { color: #909399; font-size: 12px; line-height: 1.4; margin-top: 4px; }
</style>
