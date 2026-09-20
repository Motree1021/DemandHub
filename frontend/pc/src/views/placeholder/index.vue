<template>
  <el-card shadow="never">
    <el-empty :description="`${route.meta.title || '页面'} 将在后续阶段开发`" />
  </el-card>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>
