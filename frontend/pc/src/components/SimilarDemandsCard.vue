<template>
  <el-card v-if="visible" shadow="never" class="mb16">
    <template #header>
      <div class="card-header">
        <span>相似历史需求</span>
        <el-tag size="small" type="success" effect="plain">RAG</el-tag>
      </div>
    </template>
    <el-empty v-if="!loading && !docs.length" description="暂无相似历史需求" :image-size="50" />
    <div v-for="doc in docs" :key="doc.demandId" class="sim-item" @click="$router.push(`/demand/detail/${doc.demandId}`)">
      <div class="sim-head">
        <el-link type="primary">{{ doc.demandNo }}</el-link>
        <el-tag size="small" effect="plain">{{ typeLabel(doc.demandTypeCode) }}</el-tag>
        <span class="score">相似度 {{ Math.round(doc.score * 100) }}%</span>
      </div>
      <div class="sim-title">{{ doc.title }}</div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { similarDemands, type SimilarDoc } from '@/api/agent'
import { typeLabel } from '@/utils/format'

interface Props {
  demandId: number
}

const props = defineProps<Props>()

const docs = ref<SimilarDoc[]>([])
const loading = ref(false)
const visible = ref(true)

onMounted(async () => {
  loading.value = true
  try {
    docs.value = await similarDemands(props.demandId, 5)
  } catch {
    // 知识库为空或角色不足时不展示卡片，避免干扰
    visible.value = false
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sim-item {
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
}

.sim-item:hover {
  border-color: var(--el-color-primary);
}

.sim-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.score {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.sim-title {
  font-size: 13px;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
