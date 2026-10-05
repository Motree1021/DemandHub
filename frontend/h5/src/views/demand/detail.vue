<template>
  <app-layout title="需求详情" show-back>
    <van-loading v-if="loading" class="page-loading">加载详情…</van-loading>
    <template v-else-if="detail">
      <div class="detail-card header"><div class="number">{{ demand.demandNo || `草稿 #${demand.id}` }}</div><h1>{{ demand.title || '未命名草稿' }}</h1><div class="tags"><van-tag type="primary" plain>{{ statusLabel(demand.status) }}</van-tag><van-tag plain>{{ detail.standard?.name || typeLabel(demand.demandTypeCode) }}</van-tag><van-tag :type="demand.urgency === 'NORMAL' ? 'default' : 'danger'">{{ urgencyLabel(demand.urgency) }}</van-tag></div><div class="meta"><span>期望交付：{{ demand.expectDeliveryAt || '未填写' }}</span><span>{{ demand.status === 'DRAFT' ? '保存' : '提交' }}时间：{{ fmtTime(demand.submittedAt || demand.updatedAt) }}</span><span v-if="demand.submitterName">提报人：{{ demand.submitterName }} {{ demand.submitterDept || '' }}</span></div></div>
      <div class="detail-card"><h2>需求描述</h2><p class="content">{{ demand.content || '尚未填写' }}</p></div>
      <div v-if="extensionFields.length" class="detail-card"><h2>补充信息</h2><div v-for="item in extensionFields" :key="item.path" class="ext-row"><strong>{{ item.label }}</strong><span>{{ item.value }}</span></div></div>
      <div class="detail-card"><quality-list :elements="detail.quality" :labels="labels" /></div>
      <div v-if="detail.messages.length" class="detail-card playback"><van-collapse v-model="expanded"><van-collapse-item title="AI 对话回放" name="messages"><div v-for="message in detail.messages" :key="message.id" class="history-row"><strong>{{ message.role === 'USER' ? '你' : 'AI 提报助手' }}</strong><small>{{ fmtTime(message.createdAt) }}</small><p>{{ message.content }}</p></div></van-collapse-item></van-collapse></div>
      <div v-if="demand.status === 'CLOSED'" class="detail-card"><h2>撤销说明</h2><p class="content">{{ demand.closeReason }}</p><small>{{ fmtTime(demand.closedAt) }}</small></div>
      <div class="detail-card actions">
        <van-button block plain type="primary" :loading="downloading" @click="download">下载 Markdown</van-button>
        <van-button v-if="own && demand.status === 'DRAFT'" block type="primary" @click="router.push({ path: '/report', query: { draftId: demand.id } })">继续编辑草稿</van-button>
        <van-button v-if="own && demand.status === 'SUBMITTED'" block plain type="danger" @click="closeVisible = true">撤销需求</van-button>
        <van-button block plain @click="router.push(user.userInfo?.isAdmin && !own ? '/admin' : '/mine')">{{ user.userInfo?.isAdmin && !own ? '返回需求整理' : '返回我的需求' }}</van-button>
      </div>
    </template>
    <van-empty v-else description="详情加载失败"><van-button size="small" type="primary" @click="fetchDetail">重试</van-button></van-empty>
    <van-dialog v-model:show="closeVisible" title="撤销需求" show-cancel-button :before-close="beforeClose"><van-field v-model="reason" type="textarea" rows="3" label="撤销原因" maxlength="256" placeholder="请填写撤销原因" /></van-dialog>
  </app-layout>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import QualityList from '@/components/QualityList.vue'
import { getDemand, closeDemand, downloadMarkdown, type DemandDetail, type StandardField } from '@/api/demand'
import { useUserStore } from '@/store/user'
import { allFields, fieldPath, readField } from '@/utils/form'
import { fmtTime, statusLabel, typeLabel, urgencyLabel } from '@/utils/format'
const route = useRoute(); const router = useRouter(); const user = useUserStore()
const detail = ref<DemandDetail | null>(null); const loading = ref(true); const downloading = ref(false)
const expanded = ref<string[]>([]); const closeVisible = ref(false); const reason = ref('')
const demand = computed(() => detail.value!.demand)
const own = computed(() => demand.value.submitterId === user.userInfo?.id)
const labels = computed(() => Object.fromEntries((detail.value?.standard ? allFields(detail.value.standard) : []).map(field => [field.key, field.label])))
const extensionFields = computed(() => {
  if (!detail.value) return []
  const standard = detail.value.standard
  const fields: StandardField[] = standard ? allFields(standard).filter(field => fieldPath(field).startsWith('ext.')) : Object.keys(demand.value.ext || {}).map(key => ({ key, label: key, path: `ext.${key}`, kind: 'text' as const }))
  return fields.map(field => { const value = readField(demand.value, field); return { path: fieldPath(field), label: field.label, value: field.options?.[String(value)] || (value == null || value === '' ? '未填写' : String(value)) } }).filter(item => item.value !== '未填写')
})
async function fetchDetail() { loading.value = true; try { detail.value = await getDemand(Number(route.params.id)) } catch { detail.value = null } finally { loading.value = false } }
async function download() { downloading.value = true; try { await downloadMarkdown(demand.value.id, demand.value.demandNo || `draft-${demand.value.id}`) } catch (error) { showToast(error instanceof Error ? error.message : '下载失败') } finally { downloading.value = false } }
async function beforeClose(action: string): Promise<boolean> {
  if (action === 'cancel') return true
  if (!reason.value.trim()) { showToast('请填写撤销原因'); return false }
  try { await closeDemand(demand.value.id, reason.value.trim()); await fetchDetail(); showToast('需求已撤销'); return true } catch { return false }
}
onMounted(fetchDetail)
</script>
<style scoped>
.page-loading { padding: 60px; text-align: center; }.detail-card { background: #fff; margin: 14px 12px; border-radius: 12px; padding: 18px 16px; }.number { font-size: 12px; color: #888; }.header h1 { font-size: 20px; line-height: 1.6; margin: 8px 0 14px; }.tags { display: flex; gap: 8px; flex-wrap: wrap; }.meta { display: flex; flex-direction: column; gap: 8px; margin-top: 18px; font-size: 12px; color: #888; }h2 { font-size: 15px; margin: 0 0 12px; }.content { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 14px; line-height: 1.8; margin: 0; }.ext-row { display: grid; grid-template-columns: 92px 1fr; gap: 12px; margin: 12px 0; font-size: 13px; line-height: 1.7; }.ext-row strong { font-weight: 500; color: #888; }.ext-row span { white-space: pre-wrap; overflow-wrap: anywhere; }.playback { padding: 4px 0; }.history-row { font-size: 13px; line-height: 1.8; border-bottom: 1px solid #eee; padding: 12px 0; }.history-row small { color: #999; margin-left: 10px; }.history-row p { margin: 6px 0; white-space: pre-wrap; overflow-wrap: anywhere; }.actions { display: flex; flex-direction: column; gap: 12px; padding-bottom: max(18px, env(safe-area-inset-bottom)); }
</style>
