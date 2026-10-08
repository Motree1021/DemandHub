<template>
  <div class="steps-bar">
    <div v-for="(label, index) in STEPS" :key="label" class="step" :class="{ on: index === step, done: index < step }">{{ label }}</div>
  </div>
</template>
<script setup lang="ts">
defineProps<{ step: number }>()
// 判型由 AI 自动生效（方案A：确认环节不再阻断用户），步骤收敛为四步
const STEPS = ['表达', '拆解', '追问', '提交'] as const
</script>
<style scoped>
.steps-bar { display: flex; background: linear-gradient(135deg, #1f3a8a, #2f56b8); padding: 2px 16px 10px; }
.step { flex: 1; text-align: center; font-size: 11px; color: #93a6d8; position: relative; padding-top: 15px; }
.step::before { content: ''; position: absolute; top: 3px; left: 50%; transform: translateX(-50%); width: 9px; height: 9px; border-radius: 50%; background: #4b5f96; }
.step + .step::after { content: ''; position: absolute; top: 7px; right: 50%; width: 100%; height: 2px; background: #4b5f96; }
.step.on { color: #dbeafe; font-weight: 600; }
.step.on::before { background: #60a5fa; }
.step.done { color: #86efac; }
.step.done::before { background: #16a34a; }
.step.done + .step::after { background: #16a34a; }
</style>
