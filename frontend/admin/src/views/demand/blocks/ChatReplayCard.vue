<!-- AI 对话回放卡：提报人与 AI 提报助手的引导对话全程；右栏跟随模式下填充剩余高度，内部滚动。聊天气泡布局：提报人居右、AI 居左、系统居中。 -->
<template>
  <el-card v-if="messages.length" class="replay-card">
    <template #header><span class="card-title">AI 对话回放（{{ messages.length }} 条）</span></template>
    <div class="replay">
      <div v-for="m in messages" :key="m.id" class="msg-row" :class="`from-${m.role.toLowerCase()}`">
        <div class="bubble">
          <div class="msg-head">
            <el-tag size="small" :type="m.role === 'USER' ? 'primary' : m.role === 'ASSISTANT' ? 'success' : 'info'" effect="plain">
              {{ roleLabel(m.role) }}
            </el-tag>
            <small>{{ m.createdAt }}</small>
          </div>
          <p class="msg-content">{{ m.content }}</p>
        </div>
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
.replay { flex: 1; min-height: 200px; overflow-y: auto; padding: 4px 0; }

/* 聊天气泡布局：提报人靠右、AI 靠左、系统居中 */
.msg-row { display: flex; padding: 6px 0; }
.msg-row.from-user { justify-content: flex-end; }
.msg-row.from-assistant { justify-content: flex-start; }
.msg-row.from-system { justify-content: center; }

.bubble { max-width: 78%; padding: 10px 12px; border-radius: 8px; background: #f4f6fa; border: 1px solid #eceef2; }
.from-user .bubble { background: #ecf2ff; border-color: #d9e5ff; }
.from-system .bubble { background: transparent; border: none; padding: 2px 8px; }

.msg-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.from-user .msg-head { flex-direction: row-reverse; }
.from-system .msg-head { justify-content: center; }
.msg-head small { color: #999; }
.from-system .msg-content { font-size: 12px; color: #909399; }

.msg-content { margin: 0; font-size: 13px; line-height: 1.7; white-space: pre-wrap; word-break: break-word; }
</style>
