<template>
  <el-tag v-if="urgency" size="small" :type="meta.type" disable-transitions>{{ meta.label }}</el-tag>
  <span v-else>—</span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { URGENCY_META } from '@/utils/status'

const props = defineProps<{ urgency: string | null }>()
const meta = computed(() => (props.urgency && URGENCY_META[props.urgency]) || { label: props.urgency, type: 'info' as const })
</script>
