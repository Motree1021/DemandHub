<template>
  <app-layout title="需求整理" active-tab="admin">
    <div class="filter-card">
      <h2>全部需求</h2><p>按类型、状态和提交日期整理，导出使用相同筛选条件。</p>
      <standard-field :field="typeField" :model-value="filters.type" @update:model-value="filters.type = String($event || '')" />
      <standard-field :field="statusField" :model-value="filters.status" @update:model-value="filters.status = String($event || '')" />
      <standard-field :field="{ key: 'from', label: '开始日期', kind: 'date' }" :model-value="filters.from" @update:model-value="filters.from = String($event || '')" />
      <standard-field :field="{ key: 'to', label: '截止日期', kind: 'date' }" :model-value="filters.to" @update:model-value="filters.to = String($event || '')" />
      <div class="filter-actions"><van-button type="primary" :loading="loading" @click="search">查询</van-button><van-button plain @click="reset">重置</van-button><van-button plain type="primary" :loading="downloading" @click="download">导出 XLSX</van-button></div>
    </div>
    <p class="count">共 {{ total }} 条{{ dirtyFilter ? ' · 筛选已改动，请查询后导出' : '' }}</p>
    <van-list :loading="loading" :finished="finished" :error="failed" :immediate-check="false" error-text="加载失败，点击重试" finished-text="没有更多了" @update:error="failed = $event" @load="load">
      <demand-card v-for="demand in rows" :key="demand.id" :demand="demand" show-submitter @open="router.push(`/demand/${$event}`)" />
      <van-empty v-if="!loading && !failed && !rows.length" description="当前筛选下没有需求" />
    </van-list>
  </app-layout>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import StandardField from '@/components/StandardField.vue'
import DemandCard from '@/components/DemandCard.vue'
import { adminDemands, downloadXlsx, getStandards, type DemandEntity, type StandardField as StandardFieldDefinition } from '@/api/demand'
const router = useRouter()
const filters = reactive({ type: '', status: '', from: '', to: '' }); const applied = ref({ ...filters })
const typeField = ref<StandardFieldDefinition>({ key: 'type', label: '需求类型', kind: 'enum', options: { '': '全部类型' } })
const statusField: StandardFieldDefinition = { key: 'status', label: '需求状态', kind: 'enum', options: { '': '全部状态', DRAFT: '草稿', SUBMITTED: '已提交', CLOSED: '已撤销' } }
const rows = ref<DemandEntity[]>([]); const total = ref(0); const page = ref(1); const loading = ref(false); const finished = ref(false); const failed = ref(false); const downloading = ref(false)
const dirtyFilter = computed(() => JSON.stringify(filters) !== JSON.stringify(applied.value))
let generation = 0
async function load() {
  if (loading.value || finished.value) return
  const current = generation; loading.value = true; failed.value = false
  try { const result = await adminDemands({ ...applied.value, page: page.value, size: 20 }); if (current !== generation) return; rows.value.push(...result.records); total.value = result.total; page.value++; finished.value = rows.value.length >= result.total }
  catch { if (current === generation) failed.value = true }
  finally { if (current === generation) loading.value = false }
}
async function search() {
  if (filters.from && filters.to && filters.from > filters.to) { showToast('开始日期不能晚于截止日期'); return }
  applied.value = { ...filters }; generation++; rows.value = []; total.value = 0; page.value = 1; finished.value = false; loading.value = false; await load()
}
function reset() { Object.assign(filters, { type: '', status: '', from: '', to: '' }); search() }
async function download() {
  if (dirtyFilter.value) { showToast('请先查询，导出将与列表保持相同筛选'); return }
  downloading.value = true
  try { await downloadXlsx(applied.value) } catch (error) { showToast(error instanceof Error ? error.message : '导出失败') } finally { downloading.value = false }
}
onMounted(async () => { try { const types = await getStandards(); typeField.value.options = { '': '全部类型', ...Object.fromEntries(types.map(type => [type.code, type.name])) } } catch { /* 加载错误已展示 */ } await search() })
</script>
<style scoped>
.filter-card { background: #fff; padding: 18px 4px 14px; margin: 14px 12px; border-radius: 12px; }.filter-card h2 { margin: 0 12px 6px; font-size: 19px; color: #1f3a8a; }.filter-card p { font-size: 12px; color: #888; margin: 0 12px 12px; line-height: 1.7; }.filter-actions { display: flex; gap: 10px; padding: 14px 12px 0; }.count { font-size: 12px; color: #777; padding: 0 16px; }
</style>
