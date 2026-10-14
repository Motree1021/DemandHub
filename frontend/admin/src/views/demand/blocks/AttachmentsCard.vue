<!-- 附件卡：附件清单 + 点击下载（带登录票拉 blob，只读不删）；无附件时整卡不渲染。 -->
<template>
  <el-card v-if="attachments.length">
    <template #header><span class="card-title">附件（{{ attachments.length }}）</span></template>
    <div v-for="att in attachments" :key="att.id" class="att-row" @click="onDownload(att)">
      <el-icon class="att-icon" :size="18"><Picture v-if="att.kind === 'IMAGE'" /><Document v-else /></el-icon>
      <div class="att-meta">
        <span class="att-name">{{ att.fileName }}</span>
        <small>{{ att.kindLabel }} · {{ fmtSize(att.size) }}</small>
      </div>
      <el-icon class="att-dl"><Download /></el-icon>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { Document, Download, Picture } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { AttachmentRow } from '@/api'
import { downloadFile } from '@/api/request'
import { fmtSize } from '@/utils/demand'

const props = defineProps<{ demandId: number; attachments: AttachmentRow[] }>()

async function onDownload(att: AttachmentRow) {
  try {
    await downloadFile(`/demand/${props.demandId}/attachments/${att.id}/download`, att.fileName)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '附件下载失败')
  }
}
</script>

<style scoped>
.card-title { font-weight: 600; }
.att-row { display: flex; align-items: center; gap: 10px; padding: 8px 6px; border-radius: 6px; cursor: pointer; }
.att-row:hover { background: #f5f7fa; }
.att-row + .att-row { border-top: 1px solid #f5f6f8; }
.att-icon { color: #1f3a8a; flex: none; }
.att-meta { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.att-name { font-size: 13px; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.att-meta small { color: #999; }
.att-dl { color: #999; flex: none; }
</style>
