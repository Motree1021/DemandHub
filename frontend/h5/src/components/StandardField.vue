<template>
  <div class="standard-field">
  <van-field v-if="field.kind === 'enum'" :model-value="optionLabel" :label="field.label" readonly is-link :required="field.required" :placeholder="field.placeholder || '请选择'" :disabled="disabled" @click="!disabled && (open = true)" />
  <van-field v-else-if="field.kind === 'date'" :model-value="String(modelValue || '')" :label="field.label" :required="field.required" :disabled="disabled">
    <template #input><input class="date-input" type="date" :aria-label="field.label" :value="modelValue || ''" :disabled="disabled" @change="emit('update:modelValue', ($event.target as HTMLInputElement).value || null)" /></template>
  </van-field>
  <van-field v-else-if="field.kind === 'list'" :model-value="listText" :label="field.label" :required="field.required" type="textarea" rows="2" autosize :placeholder="field.placeholder || '每行一条'" :disabled="disabled" @update:model-value="emit('update:modelValue', String($event).split('\n').map(item => item.trim()).filter(Boolean))" />
  <van-field v-else :model-value="modelValue == null ? '' : String(modelValue)" :label="field.label" :required="field.required" :type="field.kind === 'number' ? 'number' : 'textarea'" :rows="field.key === 'content' ? 4 : 1" autosize :maxlength="field.rule?.maxLen" :placeholder="field.placeholder || field.example || field.okWhen || '填写' + field.label" :disabled="disabled" @update:model-value="emit('update:modelValue', $event)" />
  <van-popup v-model:show="open" position="bottom" round>
    <van-picker :title="field.label" :columns="columns" @confirm="onConfirm" @cancel="open = false" />
  </van-popup>
  </div>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import type { StandardField } from '@/api/demand'
const props = defineProps<{ field: StandardField; modelValue: unknown; disabled?: boolean }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: unknown): void }>()
const open = ref(false)
const columns = computed(() => Object.entries(props.field.options || {}).map(([value, text]) => ({ text, value })))
const optionLabel = computed(() => props.field.options?.[String(props.modelValue ?? '')] || (props.modelValue == null ? '' : String(props.modelValue)))
const listText = computed(() => Array.isArray(props.modelValue) ? props.modelValue.join('\n') : props.modelValue == null ? '' : String(props.modelValue))
function onConfirm({ selectedOptions }: { selectedOptions: { value: string }[] }) { emit('update:modelValue', selectedOptions[0]?.value || null); open.value = false }
</script>
<style scoped>.date-input { border: 0; width: 100%; font: inherit; color: inherit; background: transparent; min-width: 0; }</style>
