<template>
  <!-- 嵌套层级卡片（2026-10-18 拍板）：需求类型权限是业务角色的「下一级」配置——
       收进同一浅色卡片（空间包含 = 下级）+ 二级灰标题降级 + 勾选业务角色后展开动画带出；
       类型权限用胶囊标签，与角色方框勾选样式区分 -->
  <div class="scoped-card">
    <div class="card-title">业务角色（可多选）</div>
    <el-checkbox-group v-model="roles">
      <el-checkbox v-for="r in scopedRoleOptions" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
    </el-checkbox-group>
    <el-collapse-transition>
      <div v-show="hasScopedRole">
        <el-divider class="inner-divider" />
        <div class="scope-title">需求类型权限</div>
        <div class="tags">
          <el-check-tag v-for="t in typeOptions" :key="t.value" :checked="types.includes(t.value)"
                        @change="toggleType(t.value)">{{ t.label }}</el-check-tag>
        </div>
        <div class="scope-tip">未选择的类型，该用户将看不到也操作不了</div>
      </div>
    </el-collapse-transition>
  </div>
</template>

<script lang="ts">
/** P4 五角色中与需求类型权限联动的业务角色（需求管理者/经理/处理人）；RoleCode/TypeCode 由下方 setup 块统一导入 */
const SCOPED_ROLES: RoleCode[] = ['EXECUTIVE', 'MANAGER', 'HANDLER']
/** 是否业务角色（卡片展开联动；用户管理页"其他角色"区、按钮置灰也复用） */
export const isScopedRole = (role: RoleCode) => SCOPED_ROLES.includes(role)
/** 需求类型选项（本卡片胶囊 + 用户管理页类型灰字短名共用） */
export const typeOptions: { value: TypeCode; label: string }[] = [
  { value: 'TECH', label: '科技需求' },
  { value: 'MATL', label: '物料需求' },
  { value: 'TRAIN', label: '培训需求' },
]
const scopedRoleOptions: { value: RoleCode; label: string }[] = [
  { value: 'EXECUTIVE', label: '管理者' },
  { value: 'MANAGER', label: '经理' },
  { value: 'HANDLER', label: '处理人' },
]
</script>

<script setup lang="ts">
import { computed } from 'vue'
import type { RoleCode, TypeCode } from '@/api'

const roles = defineModel<RoleCode[]>('roles', { required: true })
const types = defineModel<TypeCode[]>('types', { required: true })

/** 勾了任一业务角色才展开类型权限区；取消全部则收起（已选值保留，重开原样恢复） */
const hasScopedRole = computed(() => roles.value.some(isScopedRole))

function toggleType(value: TypeCode) {
  types.value = types.value.includes(value)
    ? types.value.filter(t => t !== value)
    : [...types.value, value]
}
</script>

<style scoped>
/* border-box：width:100% 含 padding，否则右边框溢出容器（content-box 会多出左右 32px） */
.scoped-card { box-sizing: border-box; width: 100%; background: var(--el-fill-color-light); border-radius: 8px; padding: 12px 16px 14px; }
/* 一级标题：业务角色（卡片的主人） */
.card-title { font-weight: 600; color: var(--el-text-color-primary); margin-bottom: 2px; }
.inner-divider { margin: 10px 0; }
/* 二级标题：类型权限（字号小一号 + 灰色，视觉上低一级） */
.scope-title { font-size: 13px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
/* 胶囊交互三态（默认灰底无边框，看不出可点）：
   未选=白底描边小按钮；悬停=描边/文字变主题色暗示可点；选中=实心主题色+前导对勾 */
.tags :deep(.el-check-tag) {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  color: var(--el-text-color-regular);
  transition: all .2s ease;
  /* 水平内边距收窄（默认 15px→10px）：为选中态对勾腾出宽度，三个同选不换行 */
  padding: 8px 10px;
}
.tags :deep(.el-check-tag:hover) {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}
.tags :deep(.el-check-tag.is-checked),
.tags :deep(.el-check-tag.is-checked:hover) {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: #fff;
}
/* 对勾紧贴文字（无尾空格），尽量少占宽度 */
.tags :deep(.el-check-tag.is-checked)::before { content: '✓'; margin-right: 2px; }
.scope-tip { color: var(--el-color-warning); font-size: 12px; margin-top: 8px; }
</style>
