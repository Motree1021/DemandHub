<template>
  <div>
    <div class="bar">
      <el-button v-if="canCreate" type="primary" size="small" @click="openEdit(null)">新建方案版本</el-button>
      <el-button size="small" :disabled="rows.length < 2" @click="compareVisible = true">版本对比</el-button>
      <el-button size="small" @click="load">刷新</el-button>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="version" label="版本" width="70">
        <template #default="{ row }">v{{ row.version }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="SOLUTION_STATUS_META[row.status]?.type">
            {{ SOLUTION_STATUS_META[row.status]?.label || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="planDeliveryAt" label="计划交付" width="110">
        <template #default="{ row }">{{ row.planDeliveryAt || '—' }}</template>
      </el-table-column>
      <el-table-column prop="authorName" label="编写人" width="100" />
      <el-table-column prop="specContent" label="需求规格" min-width="180" show-overflow-tooltip />
      <el-table-column prop="solutionContent" label="方案内容" min-width="180" show-overflow-tooltip />
      <el-table-column prop="remark" label="备注" min-width="120" show-overflow-tooltip>
        <template #default="{ row }">{{ row.remark || '—' }}</template>
      </el-table-column>
      <el-table-column prop="updatedAt" label="更新时间" width="165" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="viewRow(row)">查看</el-button>
          <el-button v-if="row.status === 'DRAFT' && row.authorId === auth.user?.id"
                     size="small" type="primary" link @click="openEdit(row)">编辑</el-button>
          <el-button v-if="row.status === 'DRAFT' && demand.status === 'ANALYZING'"
                     size="small" type="warning" link @click="submitReview(row)">提交评审</el-button>
          <el-button v-if="row.status === 'SUBMITTED' && auth.role === 'ADMIN'"
                     size="small" type="success" link @click="openReview(row)">评审</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建/编辑草稿 -->
    <el-dialog v-model="editVisible" :title="editRow ? `编辑方案 v${editRow.version}` : '新建方案版本'" width="720px">
      <el-form label-width="90px">
        <el-form-item label="需求规格">
          <el-input v-model="form.specContent" type="textarea" :rows="3" placeholder="要做什么、做到什么程度" />
        </el-form-item>
        <el-form-item label="方案内容">
          <el-input v-model="form.solutionContent" type="textarea" :rows="4" placeholder="怎么做、步骤与资源" />
        </el-form-item>
        <el-form-item label="计划交付">
          <el-date-picker v-model="form.planDeliveryAt" type="date" value-format="YYYY-MM-DD" placeholder="选择日期" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 查看全文 -->
    <el-dialog v-model="viewVisible" :title="`方案 v${viewRowData?.version} 全文`" width="720px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="需求规格"><pre class="pre">{{ viewRowData?.specContent || '—' }}</pre></el-descriptions-item>
        <el-descriptions-item label="方案内容"><pre class="pre">{{ viewRowData?.solutionContent || '—' }}</pre></el-descriptions-item>
        <el-descriptions-item label="备注">{{ viewRowData?.remark || '—' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <!-- 评审 -->
    <el-dialog v-model="reviewVisible" :title="`评审方案 v${reviewRow?.version}`" width="480px">
      <el-form label-width="90px">
        <el-form-item label="评审结果" required>
          <el-radio-group v-model="reviewForm.result">
            <el-radio value="PASS">通过</el-radio>
            <el-radio value="REJECT">打回</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="reviewForm.result === 'REJECT' ? '打回意见' : '评审意见'" :required="reviewForm.result === 'REJECT'">
          <el-input v-model="reviewForm.opinion" type="textarea" :rows="3"
                    :placeholder="reviewForm.result === 'REJECT' ? '打回必须填写意见' : '选填'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="saveReview">提交评审</el-button>
      </template>
    </el-dialog>

    <!-- 版本对比 -->
    <el-dialog v-model="compareVisible" title="方案版本对比" width="860px">
      <div class="compare-bar">
        <el-select v-model="compareV1" placeholder="版本1" class="ver-sel">
          <el-option v-for="r in rows" :key="r.version" :label="`v${r.version}`" :value="r.version" />
        </el-select>
        <span class="vs">对比</span>
        <el-select v-model="compareV2" placeholder="版本2" class="ver-sel">
          <el-option v-for="r in rows" :key="r.version" :label="`v${r.version}`" :value="r.version" />
        </el-select>
        <el-button type="primary" size="small" :disabled="!compareV1 || !compareV2 || compareV1 === compareV2"
                   @click="doCompare">对比</el-button>
      </div>
      <el-table v-if="compareItems.length" :data="compareItems" border>
        <el-table-column prop="field" label="字段" width="110" />
        <el-table-column :label="`v${compareV1}`" min-width="320">
          <template #default="{ row }"><pre class="pre">{{ row.a }}</pre></template>
        </el-table-column>
        <el-table-column :label="`v${compareV2}`" min-width="320">
          <template #default="{ row }"><pre class="pre">{{ row.b }}</pre></template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { solutionApi } from '@/api'
import type { DemandRow, SolutionRow } from '@/api'
import { ApiError } from '@/api/request'
import { SOLUTION_STATUS_META } from '@/utils/status'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ demand: DemandRow }>()
const emit = defineEmits<{ reload: [] }>()
const auth = useAuthStore()

const loading = ref(false)
const submitting = ref(false)
const rows = ref<SolutionRow[]>([])

/** 分析中才允许新建版本（后端同样强校验） */
const canCreate = computed(() =>
  props.demand.status === 'ANALYZING' &&
  (props.demand.assigneeId === auth.user?.id || auth.role === 'ADMIN'))

function errorMessage(e: unknown, fallback: string) {
  return e instanceof ApiError ? e.message : fallback
}

async function load() {
  loading.value = true
  try {
    rows.value = await solutionApi.list(props.demand.id)
  } catch (e) {
    ElMessage.error(errorMessage(e, '加载失败'))
  } finally {
    loading.value = false
  }
}

// ---- 新建/编辑 ----
const editVisible = ref(false)
const editRow = ref<SolutionRow | null>(null)
const form = reactive({ specContent: '', solutionContent: '', planDeliveryAt: '', remark: '' })

function openEdit(row: SolutionRow | null) {
  editRow.value = row
  form.specContent = row?.specContent || ''
  form.solutionContent = row?.solutionContent || ''
  form.planDeliveryAt = row?.planDeliveryAt || ''
  form.remark = row?.remark || ''
  editVisible.value = true
}

async function saveEdit() {
  submitting.value = true
  try {
    const payload = {
      specContent: form.specContent || undefined,
      solutionContent: form.solutionContent || undefined,
      planDeliveryAt: form.planDeliveryAt || undefined,
      remark: form.remark || undefined,
    }
    if (editRow.value) {
      await solutionApi.update(editRow.value.id, payload)
    } else {
      await solutionApi.create({ demandId: props.demand.id, ...payload })
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

// ---- 查看 ----
const viewVisible = ref(false)
const viewRowData = ref<SolutionRow | null>(null)
function viewRow(row: SolutionRow) {
  viewRowData.value = row
  viewVisible.value = true
}

// ---- 提交评审 ----
async function submitReview(row: SolutionRow) {
  try {
    await ElMessageBox.confirm(`提交方案 v${row.version} 进入评审？提交后内容不可再修改。`, '提交评审',
      { type: 'warning', confirmButtonText: '提交', cancelButtonText: '取消' })
  } catch { return }
  try {
    await solutionApi.submitReview(row.id)
    ElMessage.success('已提交评审')
    emit('reload') // 需求状态进入「方案待评审」
  } catch (e) {
    ElMessage.error(errorMessage(e, '提交失败'))
  }
}

// ---- 评审 ----
const reviewVisible = ref(false)
const reviewRow = ref<SolutionRow | null>(null)
const reviewForm = reactive({ result: 'PASS' as 'PASS' | 'REJECT', opinion: '' })

function openReview(row: SolutionRow) {
  reviewRow.value = row
  reviewForm.result = 'PASS'
  reviewForm.opinion = ''
  reviewVisible.value = true
}

async function saveReview() {
  if (reviewForm.result === 'REJECT' && !reviewForm.opinion.trim()) {
    ElMessage.warning('打回必须填写意见')
    return
  }
  if (!reviewRow.value) return
  submitting.value = true
  try {
    await solutionApi.review(reviewRow.value.id, reviewForm.result, reviewForm.opinion.trim() || undefined)
    ElMessage.success(reviewForm.result === 'PASS' ? '已通过，需求进入「已确认」' : '已打回，需求回到「分析中」')
    reviewVisible.value = false
    emit('reload')
  } catch (e) {
    ElMessage.error(errorMessage(e, '评审失败'))
  } finally {
    submitting.value = false
  }
}

// ---- 对比 ----
const compareVisible = ref(false)
const compareV1 = ref<number>()
const compareV2 = ref<number>()
const compareItems = ref<{ field: string; a: string; b: string }[]>([])

async function doCompare() {
  if (!compareV1.value || !compareV2.value) return
  try {
    const data = await solutionApi.compare(props.demand.id, compareV1.value, compareV2.value)
    const [a, b] = data.items
    compareItems.value = [
      { field: '需求规格', a: a?.specContent || '—', b: b?.specContent || '—' },
      { field: '方案内容', a: a?.solutionContent || '—', b: b?.solutionContent || '—' },
      { field: '计划交付', a: a?.planDeliveryAt || '—', b: b?.planDeliveryAt || '—' },
      { field: '备注', a: a?.remark || '—', b: b?.remark || '—' },
    ]
  } catch (e) {
    ElMessage.error(errorMessage(e, '对比失败'))
  }
}

onMounted(load)
</script>

<style scoped>
.bar { display: flex; gap: 8px; margin-bottom: 12px; }
.pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-family: inherit; }
.compare-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.ver-sel { width: 120px; }
.vs { color: #909399; }
</style>
