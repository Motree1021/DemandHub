<template>
  <app-layout title="我的需求" active-tab="mine">
    <van-tabs v-model:active="status" sticky offset-top="46" @change="refresh">
      <van-tab title="全部" name="" /><van-tab title="草稿" name="DRAFT" /><van-tab title="已提交" name="SUBMITTED" /><van-tab title="已撤销" name="CLOSED" />
    </van-tabs>
    <van-pull-refresh v-model="refreshing" @refresh="refresh">
      <van-list :loading="loading" :finished="finished" :error="failed" error-text="加载失败，点击重试" :immediate-check="false" finished-text="没有更多了" @update:error="failed = $event" @load="load">
        <demand-card v-for="demand in rows" :key="demand.id" :demand="demand" @open="router.push(`/demand/${$event}`)" />
        <van-empty v-if="!loading && !failed && !rows.length" description="暂无需求，可先保存一份草稿" />
      </van-list>
    </van-pull-refresh>
  </app-layout>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppLayout from '@/components/AppLayout.vue'
import DemandCard from '@/components/DemandCard.vue'
import { myDemands, type DemandEntity } from '@/api/demand'
const router = useRouter(); const status = ref(''); const rows = ref<DemandEntity[]>([])
const page = ref(1); const loading = ref(false); const refreshing = ref(false); const finished = ref(false); const failed = ref(false)
let generation = 0
async function load() {
  if (loading.value || finished.value) return
  const current = generation; loading.value = true; failed.value = false
  try {
    const data = await myDemands({ page: page.value, size: 15, ...(status.value ? { status: status.value } : {}) })
    if (current !== generation) return
    rows.value.push(...data.records); page.value++; finished.value = rows.value.length >= data.total
  } catch { if (current === generation) failed.value = true }
  finally { if (current === generation) loading.value = false }
}
async function refresh() { generation++; loading.value = false; rows.value = []; page.value = 1; finished.value = false; try { await load() } finally { refreshing.value = false } }
onMounted(refresh)
</script>
