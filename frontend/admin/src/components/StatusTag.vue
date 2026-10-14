<template>
  <span class="status-tag">
    <el-tag size="small" :type="meta.type" disable-transitions>{{ meta.label }}</el-tag>
    <el-tooltip v-if="onHold" :content="holdReason ? `挂起原因：${holdReason}` : '已挂起'" placement="top">
      <el-tag size="small" type="danger" disable-transitions>挂起</el-tag>
    </el-tooltip>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { STATUS_META } from '@/utils/status'

const props = defineProps<{ status: string; onHold?: boolean; holdReason?: string | null }>()
const meta = computed(() => STATUS_META[props.status] || { label: props.status, type: 'info' as const })
</script>

<style scoped>
.status-tag { display: inline-flex; gap: 4px; align-items: center; }
</style>
