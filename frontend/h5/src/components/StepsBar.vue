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
/* 白卡浮起：步骤条从深蓝通栏改为页面灰底上的白色圆角卡片，与原生深色导航栏断开层次 */
.steps-bar {
  display: flex;
  margin: 10px 12px 2px;
  padding: 12px 8px 10px;
  background: #fff;
  border: 1px solid #eef0f5;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(31, 58, 138, 0.06);
  counter-reset: step;
}
.step {
  flex: 1;
  position: relative;
  text-align: center;
  padding-top: 28px;
  font-size: 12px;
  color: #9aa4b5;
  counter-increment: step;
}
/* 连接线（::after）在圆点（::before）之下，避免线段两端盖住圆点 */
.step + .step::after {
  content: '';
  position: absolute;
  z-index: 0;
  top: 11px;
  right: 50%;
  width: 100%;
  height: 2px;
  background: #e3e8f0;
}
.step::before {
  content: counter(step);
  position: absolute;
  z-index: 1;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fff;
  border: 1.5px solid #d3dae6;
  color: #9aa4b5;
  font-size: 12px;
  font-weight: 600;
  line-height: 20px;
  box-sizing: border-box;
}
.step.on { color: #1f3a8a; font-weight: 600; }
.step.on::before { background: #1f3a8a; border-color: #1f3a8a; color: #fff; }
.step.done { color: #5b6b8c; }
.step.done::before { content: '✓'; background: #fff; border-color: #1f3a8a; color: #1f3a8a; font-size: 11px; }
.step.done + .step::after { background: #1f3a8a; }
</style>
