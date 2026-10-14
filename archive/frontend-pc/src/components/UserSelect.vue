<template>
  <el-select
    :model-value="modelValue"
    filterable
    remote
    clearable
    :remote-method="onSearch"
    :loading="loading"
    :placeholder="placeholder"
    style="width: 100%"
    @update:model-value="onChange"
    @focus="onFocus"
  >
    <el-option v-for="u in options" :key="u.id" :label="u.name" :value="u.id">
      <span>{{ u.name }}</span>
      <span class="user-select-dept">{{ u.deptPath || u.userId }}</span>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { searchUsers, type UserSnapshotVO } from '@/api/directory'

const props = withDefaults(
  defineProps<{
    modelValue: number | null | undefined
    placeholder?: string
    /** 限定某组织子树（orgId 前缀过滤），用于分派时只看本组织人员 */
    orgPathPrefix?: string
  }>(),
  { placeholder: '搜索姓名 / 用户ID' }
)

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
  select: [user: UserSnapshotVO | null]
}>()

const loading = ref(false)
const options = ref<UserSnapshotVO[]>([])

async function onSearch(keyword: string) {
  loading.value = true
  try {
    let list = await searchUsers(keyword)
    if (props.orgPathPrefix) {
      list = list.filter((u) => (u.deptPath || '').includes(props.orgPathPrefix as string))
    }
    // 保证已选值在选项中
    if (props.modelValue && !list.some((u) => u.id === props.modelValue)) {
      const all = await searchUsers('')
      const cur = all.find((u) => u.id === props.modelValue)
      if (cur) {
        list = [cur, ...list]
      }
    }
    options.value = list
  } finally {
    loading.value = false
  }
}

function onFocus() {
  if (!options.value.length) {
    onSearch('')
  }
}

function onChange(val: number | null) {
  emit('update:modelValue', val)
  emit('select', options.value.find((u) => u.id === val) || null)
}
</script>

<style scoped>
.user-select-dept {
  float: right;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-left: 12px;
}
</style>
