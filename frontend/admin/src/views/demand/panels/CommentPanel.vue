<template>
  <div>
    <div class="add-bar">
      <el-input v-model="newContent" type="textarea" :rows="2" placeholder="补充说明、进展同步…" class="add-input" />
      <el-button type="primary" :loading="submitting" :disabled="!newContent.trim()" @click="add">发表</el-button>
    </div>

    <el-empty v-if="!loading && !rows.length" description="暂无沟通记录" />
    <div v-for="row in rows" :key="row.id" class="item">
      <div class="meta">
        <span class="author">{{ row.authorName || '—' }}</span>
        <span class="time">{{ row.createdAt }}<template v-if="row.updatedAt !== row.createdAt">（已编辑）</template></span>
        <el-button v-if="row.authorId === auth.user?.id" size="small" link type="primary"
                   @click="openEdit(row)">编辑</el-button>
      </div>
      <pre class="content">{{ row.content }}</pre>
    </div>

    <el-dialog v-model="editVisible" title="编辑沟通记录" width="520px">
      <el-input v-model="editContent" type="textarea" :rows="4" />
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!editContent.trim()" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { commentApi } from '@/api'
import type { CommentRow } from '@/api'
import { ApiError } from '@/api/request'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ demandId: number }>()
const auth = useAuthStore()

const loading = ref(false)
const submitting = ref(false)
const rows = ref<CommentRow[]>([])
const newContent = ref('')

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function load() {
  loading.value = true
  try {
    rows.value = await commentApi.list(props.demandId)
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

async function add() {
  submitting.value = true
  try {
    await commentApi.add(props.demandId, newContent.value.trim())
    newContent.value = ''
    await load()
  } catch (e) {
    ElMessage.error(errorMessage(e, '发表失败'))
  } finally {
    submitting.value = false
  }
}

const editVisible = ref(false)
const editId = ref<number>(0)
const editContent = ref('')

function openEdit(row: CommentRow) {
  editId.value = row.id
  editContent.value = row.content
  editVisible.value = true
}

async function saveEdit() {
  submitting.value = true
  try {
    await commentApi.update(editId.value, editContent.value.trim())
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
.add-bar { display: flex; gap: 8px; align-items: flex-end; margin-bottom: 16px; }
.add-input { flex: 1; }
.item { padding: 10px 0; border-bottom: 1px solid #ebeef5; }
.meta { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.author { font-weight: 600; font-size: 13px; }
.time { color: #909399; font-size: 12px; }
.content { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; }
</style>
