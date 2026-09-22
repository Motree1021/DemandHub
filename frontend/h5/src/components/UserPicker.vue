<template>
  <!-- 只读展示框，点击弹出选人面板；hideField 场景仅保留弹层 -->
  <van-field
    v-if="!hideField"
    :model-value="displayText"
    :label="label"
    :placeholder="placeholder"
    readonly
    is-link
    v-bind="$attrs"
    @click="open"
  />

  <van-popup v-model:show="visible" position="bottom" round :style="{ height: '70%' }">
    <div class="picker-panel">
      <div class="picker-header">
        <span class="picker-title">{{ title }}</span>
        <van-button size="small" type="primary" :disabled="multiple && !selectedIds.length" @click="onConfirm">确定</van-button>
      </div>
      <van-search v-model="keyword" placeholder="搜索姓名 / 账号" />
      <div class="picker-list">
        <van-cell
          v-for="u in filtered"
          :key="u.id"
          :title="u.name"
          :label="u.deptPath || u.userId"
          clickable
          @click="onPick(u)"
        >
          <template #right-icon>
            <van-icon v-if="isChecked(u.id)" name="success" color="#1F3A8A" />
          </template>
        </van-cell>
        <van-empty v-if="!filtered.length" description="未找到匹配用户" />
      </div>
    </div>
  </van-popup>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listAllUsers, type UserSnapshotVO } from '@/api/directory'

const props = withDefaults(
  defineProps<{
    /** 单选传 number|null；多选传 number[] */
    modelValue: number | number[] | null
    multiple?: boolean
    label?: string
    title?: string
    placeholder?: string
    /** 隐藏触发输入框（由外部 v-model:visible 控制弹层） */
    hideField?: boolean
    /** 外部控制弹层显隐 */
    visible?: boolean
  }>(),
  { multiple: false, label: '', title: '选择人员', placeholder: '请选择', hideField: false, visible: undefined }
)

const emit = defineEmits<{
  'update:modelValue': [val: number | number[] | null]
  'update:visible': [val: boolean]
  confirm: [users: UserSnapshotVO[]]
}>()

const innerVisible = ref(false)
const keyword = ref('')
const users = ref<UserSnapshotVO[]>([])
const selectedIds = ref<number[]>([])

const visible = computed({
  get: () => (props.visible !== undefined ? props.visible : innerVisible.value),
  set: (v) => {
    innerVisible.value = v
    emit('update:visible', v)
    if (v) {
      syncFromModel()
    }
  }
})

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) {
    return users.value
  }
  return users.value.filter((u) => u.name.toLowerCase().includes(kw) || u.userId.toLowerCase().includes(kw))
})

const displayText = computed(() => {
  const ids = Array.isArray(props.modelValue) ? props.modelValue : props.modelValue != null ? [props.modelValue] : []
  if (!ids.length) {
    return ''
  }
  return users.value
    .filter((u) => ids.includes(u.id))
    .map((u) => u.name)
    .join('、')
})

function isChecked(id: number): boolean {
  return selectedIds.value.includes(id)
}

function syncFromModel() {
  const cur = Array.isArray(props.modelValue) ? props.modelValue : props.modelValue != null ? [props.modelValue] : []
  selectedIds.value = [...cur]
  keyword.value = ''
}

async function open() {
  await ensureUsers()
  visible.value = true
}

// 外部 v-model:visible 打开时也同步一次用户与选中态
watch(
  () => props.visible,
  async (v) => {
    if (v) {
      await ensureUsers()
      syncFromModel()
    }
  }
)

function onPick(u: UserSnapshotVO) {
  if (props.multiple) {
    const idx = selectedIds.value.indexOf(u.id)
    if (idx >= 0) {
      selectedIds.value.splice(idx, 1)
    } else {
      selectedIds.value.push(u.id)
    }
  } else {
    selectedIds.value = [u.id]
    onConfirm()
  }
}

function onConfirm() {
  const val: number | number[] | null = props.multiple ? [...selectedIds.value] : selectedIds.value[0] ?? null
  emit('update:modelValue', val)
  emit(
    'confirm',
    users.value.filter((u) => selectedIds.value.includes(u.id))
  )
  visible.value = false
}

async function ensureUsers() {
  if (!users.value.length) {
    users.value = await listAllUsers()
  }
}

// 挂载即预热，保证未打开弹层时也能正确回显已选姓名
onMounted(() => {
  ensureUsers()
})
</script>

<style scoped>
.picker-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.picker-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px 6px;
}

.picker-title {
  font-size: 16px;
  font-weight: 600;
}

.picker-list {
  flex: 1;
  overflow-y: auto;
}
</style>
