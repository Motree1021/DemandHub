<template>
  <router-view />
</template>

<script setup lang="ts">
// 输入框聚焦时自动上推，避免被手机键盘遮挡（检查点 2）
document.addEventListener('focusin', (e) => {
  const el = e.target as HTMLElement | null
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
    // 等键盘弹起动画后再滚动
    setTimeout(() => {
      el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 300)
  }
})
</script>

<style>
/* 全局主题：主色对齐创金零售深蓝 #1F3A8A */
:root {
  --van-primary-color: #1F3A8A;
  --van-danger-color: #ff4757;
}

* {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  padding: 0;
  background: #f5f6f8;
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  /* 禁止移动端双击缩放带来的 300ms 延迟之外的横向滚动 */
  overflow-x: hidden;
}

#app {
  min-height: 100vh;
}
</style>
