<template>
  <app-layout title="验收评价" show-back>
    <div v-if="detail" class="page">
      <!-- 需求概要 -->
      <div class="card">
        <div class="demand-no">{{ detail.demand.demandNo }}</div>
        <div class="demand-title">{{ detail.demand.title }}</div>
        <div class="demand-meta">提报人：{{ detail.submitterName || '-' }} · 承接：{{ detail.assigneeOrgName || '-' }}</div>
      </div>

      <!-- 星级评分 -->
      <div class="card">
        <div class="card-title">验收评分</div>
        <div class="rate-row">
          <span class="rate-label">质量分</span>
          <van-rate v-model="qualityScore" :size="28" color="#f59e0b" void-color="#e5e7eb" />
        </div>
        <div class="rate-row">
          <span class="rate-label">满意度</span>
          <van-rate v-model="satisfactionScore" :size="28" color="#f59e0b" void-color="#e5e7eb" />
        </div>
        <van-field
          v-model="comment"
          label="验收意见"
          type="textarea"
          rows="4"
          maxlength="500"
          show-word-limit
          placeholder="通过时选填；打回时请说明原因"
        />
      </div>

      <!-- 操作按钮（≥44px） -->
      <div class="btn-bar">
        <van-button type="success" block class="op-btn" :loading="submitting === 'PASS'" @click="onSubmit('PASS')">验收通过</van-button>
        <van-button type="danger" block plain class="op-btn" :loading="submitting === 'REJECT'" @click="onSubmit('REJECT')">打回整改</van-button>
      </div>
    </div>
  </app-layout>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showSuccessToast, showToast } from 'vant'
import AppLayout from '@/components/AppLayout.vue'
import { getDemand, acceptanceReview, type DemandDetail } from '@/api/demand'

const route = useRoute()
const router = useRouter()
const demandId = Number(route.params.id)

const detail = ref<DemandDetail | null>(null)
const qualityScore = ref(0)
const satisfactionScore = ref(0)
const comment = ref('')
const submitting = ref('')

async function onSubmit(conclusion: 'PASS' | 'REJECT') {
  if (conclusion === 'PASS' && (!qualityScore.value || !satisfactionScore.value)) {
    showToast('验收通过请先完成质量分与满意度评分')
    return
  }
  if (conclusion === 'REJECT' && !comment.value.trim()) {
    showToast('打回时请填写验收意见说明原因')
    return
  }
  submitting.value = conclusion
  try {
    await acceptanceReview(demandId, {
      conclusion,
      qualityScore: qualityScore.value || undefined,
      satisfactionScore: satisfactionScore.value || undefined,
      comment: comment.value.trim() || undefined
    })
    showSuccessToast(conclusion === 'PASS' ? '验收已通过' : '已打回整改')
    router.replace(`/demand/${demandId}`)
  } finally {
    submitting.value = ''
  }
}

onMounted(async () => {
  detail.value = await getDemand(demandId)
})
</script>

<style scoped>
.card {
  background: #fff;
  border-radius: 14px;
  margin: 12px 12px 0;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.demand-no {
  font-size: 12px;
  color: #888;
}

.demand-title {
  font-size: 16px;
  font-weight: 600;
  margin-top: 4px;
}

.demand-meta {
  font-size: 12px;
  color: #999;
  margin-top: 6px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  border-left: 3px solid #1F3A8A;
  padding-left: 8px;
  margin-bottom: 14px;
}

.rate-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 0 12px;
}

.rate-label {
  font-size: 14px;
  color: #666;
  width: 60px;
  flex-shrink: 0;
}

.btn-bar {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.op-btn {
  height: 46px;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
}
</style>
