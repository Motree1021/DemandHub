<!-- AI 对话回放卡：提报人与 AI 提报助手的引导对话全程；右栏跟随模式下填充剩余高度，内部滚动。 -->
<template>
  <el-card v-if="messages.length" class="replay-card">
    <template #header><span class="card-title">AI 对话回放（{{ messages.length }} 条）</span></template>
    <div class="replay">
      <div v-for="m in messages" :key="m.id" class="msg-row">
        <div class="msg-head">
          <el-tag size="small" :type="m.role === 'USER' ? 'primary' : 'success'" effect="plain">
            {{ roleLabel(m.role) }}
          </el-tag>
          <small>{{ m.createdAt }}</small>
        </div>
        <p class="msg-content">{{ m.content }}</p>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import type { MessageRow } from '@/api'

defineProps<{ messages: MessageRow[] }>()

function roleLabel(role: MessageRow['role']): string {
  return role === 'USER' ? '提报人' : role === 'ASSISTANT' ? 'AI 提报助手' : '系统'
}
</script>

<style scoped>
/* 跟随左栏：卡片纵向 flex，父级（side-col）给 .grow 分配剩余高度 */
.replay-card { display: flex; flex-direction: column; }
.replay-card :deep(.el-card__body) { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.card-title { font-weight: 600; }
.replay { flex: 1; min-height: 200px; overflow-y: auto; }
.msg-row { padding: 8px 0; border-bottom: 1px solid #f1f2f4; }
.msg-row:last-child { border-bottom: none; }
.msg-head { display: flex; align-items: center; gap: 8px; }
.msg-head small { color: #999; }
.msg-content { margin: 6px 0 0; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
</style>
