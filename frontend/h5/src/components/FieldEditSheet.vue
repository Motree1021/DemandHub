<template>
  <van-popup :show="show" position="bottom" round @update:show="emit('update:show', $event)">
    <div v-if="field" class="field-edit">
      <h3>修改「{{ field.label }}」</h3>
      <p v-if="field.example || field.okWhen" class="tip">示例：{{ field.example || field.okWhen }}</p>
      <standard-field :field="field" :model-value="local" @update:model-value="local = $event" />
      <div class="btns">
        <van-button block @click="emit('update:show', false)">取消</van-button>
        <van-button block type="primary" @click="confirm">确认修改</van-button>
      </div>
    </div>
  </van-popup>
</template>
<script setup lang="ts">
import { ref, watch } from 'vue'
import StandardField from './StandardField.vue'
import type { StandardField as StandardFieldDefinition } from '@/api/demand'
const props = defineProps<{ show: boolean; field: StandardFieldDefinition | null; value: unknown }>()
const emit = defineEmits<{ (event: 'update:show', value: boolean): void; (event: 'save', field: StandardFieldDefinition, value: unknown): void }>()
const local = ref<unknown>(null)
watch(() => [props.show, props.field], () => { if (props.show) local.value = Array.isArray(props.value) ? [...props.value] : props.value })
function confirm() { if (props.field) emit('save', props.field, local.value); emit('update:show', false) }
</script>
<style scoped>
.field-edit { padding: 20px 16px max(16px, env(safe-area-inset-bottom)); }
h3 { margin: 0 0 6px; font-size: 16px; }
.tip { font-size: 12px; color: #888; line-height: 1.7; margin: 0 0 12px; }
.btns { display: flex; gap: 12px; margin-top: 16px; }
.btns .van-button { flex: 1; }
</style>
