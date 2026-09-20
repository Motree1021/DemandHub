<template>
  <div class="dashboard">
    <el-row :gutter="16">
      <el-col :span="6" v-for="card in cards" :key="card.title">
        <el-card shadow="hover" class="kpi-card">
          <div class="kpi-title">{{ card.title }}</div>
          <div class="kpi-value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>
    <el-card shadow="never" class="welcome-card">
      <el-empty description="DemandHub 脚手架已启动，业务页面将在阶段 5 开发" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
// 阶段 7 接入看板真实数据，当前为占位
const cards = [
  { title: '本月新增', value: '--' },
  { title: '在途需求', value: '--' },
  { title: '已完成', value: '--' },
  { title: '超 SLA', value: '--' }
]
</script>

<style scoped>
.kpi-card {
  text-align: center;
}

.kpi-title {
  color: #909399;
  font-size: 14px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 600;
  color: #1a3a6b;
  margin-top: 8px;
}

.welcome-card {
  margin-top: 16px;
}
</style>
