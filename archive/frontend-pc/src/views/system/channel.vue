<template>
  <div class="channel-page">
    <el-card>
      <el-table :data="channels" v-loading="loading" border>
        <el-table-column prop="channelCode" label="渠道编码" width="110" />
        <el-table-column prop="channelName" label="渠道名称" width="140" />
        <el-table-column prop="appId" label="AppID" width="140" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'ACTIVE' ? 'success' : 'info'">
              {{ row.status === 'ACTIVE' ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="SSO已配置" width="100">
          <template #default="{ row }">
            <el-tag :type="row.ssoConfigured ? 'success' : 'info'">{{ row.ssoConfigured ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="SSO校验地址" min-width="200">
          <template #default="{ row }">{{ row.ssoVerifyBaseUrl || '—' }}</template>
        </el-table-column>
        <el-table-column label="AppKey" width="120">
          <template #default="{ row }">{{ row.appKey || '—' }}</template>
        </el-table-column>
        <el-table-column label="AppSecret" width="110">
          <template #default="{ row }">{{ row.appSecret || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-switch
              :model-value="row.status === 'ACTIVE'"
              inline-prompt
              active-text="启"
              inactive-text="停"
              class="status-switch"
              @change="onToggleStatus(row, $event)"
            />
            <el-button link type="primary" @click="openConfig(row)">配置</el-button>
            <el-button link type="primary" :loading="testLoadingId === row.id" @click="onTest(row)">连接测试</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="unmapped-card">
      <div class="toolbar">
        <el-select v-model="unmappedQuery.channelCode" placeholder="渠道" clearable style="width: 200px" @change="loadUnmapped(1)">
          <el-option v-for="c in channels" :key="c.channelCode" :label="`${c.channelName}（${c.channelCode}）`" :value="c.channelCode" />
        </el-select>
        <el-button type="primary" @click="loadUnmapped(1)">查询</el-button>
        <span class="hint">校准方式：在组织管理中为目标组织维护 external_dept_id 后删除本记录</span>
      </div>

      <el-table :data="unmappedRows" v-loading="unmappedLoading" border>
        <el-table-column prop="channelCode" label="渠道" width="100" />
        <el-table-column prop="deptId" label="部门ID" width="120" />
        <el-table-column prop="deptName" label="部门名称" width="150" />
        <el-table-column prop="deptPath" label="部门路径" min-width="200">
          <template #default="{ row }">{{ row.deptPath || '—' }}</template>
        </el-table-column>
        <el-table-column prop="sampleChannelUserId" label="样本渠道用户ID" width="150" />
        <el-table-column prop="hitCount" label="命中次数" width="90" />
        <el-table-column label="最近命中时间" width="150">
          <template #default="{ row }">{{ fmtTime(row.lastSeenAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除该未映射记录？" @confirm="onDeleteUnmapped(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="unmappedTotal"
        :page-size="unmappedQuery.size"
        :current-page="unmappedQuery.current"
        @current-change="loadUnmapped"
      />
    </el-card>

    <!-- 渠道配置 -->
    <el-dialog v-model="configVisible" :title="`配置渠道 - ${currentRow?.channelName || ''}`" width="560px">
      <el-form :model="configForm" label-width="140px">
        <el-form-item label="AppID">
          <el-input v-model="configForm.appId" placeholder="AppID" />
        </el-form-item>
        <el-form-item label="SSO校验地址">
          <el-input v-model="configForm.ssoVerifyBaseUrl" placeholder="SSO ticket 校验基础地址" />
        </el-form-item>
        <el-form-item label="AppKey">
          <el-input v-model="configForm.appKey" placeholder="AppKey" />
        </el-form-item>
        <el-form-item label="AppSecret">
          <el-input v-model="configForm.appSecret" type="password" show-password placeholder="留空表示不更换密钥" />
        </el-form-item>
        <el-form-item label="Ticket有效期(秒)">
          <el-input-number v-model="configForm.ticketTtlSeconds" :min="1" :max="86400" style="width: 100%" />
        </el-form-item>
        <el-form-item label="超时时间(毫秒)">
          <el-input-number v-model="configForm.timeoutMs" :min="100" :max="60000" :step="500" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onConfigSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listChannels,
  updateChannelStatus,
  updateChannelConfig,
  testChannel,
  pageDeptUnmapped,
  deleteDeptUnmapped
} from '@/api/system'
import type { ChannelVO, ChannelConfigRequest, DeptUnmapped } from '@/api/system'
import { fmtTime } from '@/utils/format'

/* ---------- 渠道列表 ---------- */
const channels = ref<ChannelVO[]>([])
const loading = ref(false)
const saving = ref(false)
const testLoadingId = ref<number | null>(null)
const currentRow = ref<ChannelVO | null>(null)

async function loadChannels() {
  loading.value = true
  try {
    channels.value = await listChannels()
  } finally {
    loading.value = false
  }
}

async function onToggleStatus(row: ChannelVO, val: string | number | boolean) {
  const target: 'ACTIVE' | 'DISABLED' = val ? 'ACTIVE' : 'DISABLED'
  try {
    await ElMessageBox.confirm(`确认${val ? '启用' : '停用'}渠道「${row.channelName}」？`, '提示', {
      type: 'warning',
      confirmButtonText: '确认',
      cancelButtonText: '取消'
    })
  } catch {
    // 取消：:model-value 未变更，开关自动回弹
    return
  }
  await updateChannelStatus(row.id, target)
  ElMessage.success(val ? '已启用' : '已停用')
  loadChannels()
}

/* ---------- 配置 ---------- */
const configVisible = ref(false)
const configForm = reactive({
  appId: '',
  ssoVerifyBaseUrl: '',
  appKey: '',
  appSecret: '',
  ticketTtlSeconds: undefined as number | undefined,
  timeoutMs: undefined as number | undefined
})

function openConfig(row: ChannelVO) {
  currentRow.value = row
  Object.assign(configForm, {
    appId: row.appId || '',
    ssoVerifyBaseUrl: row.ssoVerifyBaseUrl || '',
    appKey: row.appKey || '',
    appSecret: '',
    ticketTtlSeconds: row.ticketTtlSeconds ?? undefined,
    timeoutMs: row.timeoutMs ?? undefined
  })
  configVisible.value = true
}

async function onConfigSave() {
  saving.value = true
  try {
    const payload: ChannelConfigRequest = {
      appId: configForm.appId || undefined,
      ssoVerifyBaseUrl: configForm.ssoVerifyBaseUrl || undefined,
      appKey: configForm.appKey || undefined,
      ticketTtlSeconds: configForm.ticketTtlSeconds,
      timeoutMs: configForm.timeoutMs
    }
    if (configForm.appSecret) {
      payload.appSecret = configForm.appSecret
    }
    await updateChannelConfig(currentRow.value!.id, payload)
    ElMessage.success('配置已保存')
    configVisible.value = false
    loadChannels()
  } finally {
    saving.value = false
  }
}

/* ---------- 连接测试 ---------- */
async function onTest(row: ChannelVO) {
  testLoadingId.value = row.id
  try {
    const result = await testChannel(row.id)
    ElMessageBox.alert(result || '测试完成', '连接测试结果', { confirmButtonText: '知道了' })
  } finally {
    testLoadingId.value = null
  }
}

/* ---------- 部门未映射 ---------- */
const unmappedQuery = reactive({ current: 1, size: 10, channelCode: '' })
const unmappedRows = ref<DeptUnmapped[]>([])
const unmappedTotal = ref(0)
const unmappedLoading = ref(false)

async function loadUnmapped(current = unmappedQuery.current) {
  unmappedQuery.current = current
  unmappedLoading.value = true
  try {
    const data = await pageDeptUnmapped({
      current: unmappedQuery.current,
      size: unmappedQuery.size,
      channelCode: unmappedQuery.channelCode || undefined
    })
    unmappedRows.value = data.records
    unmappedTotal.value = data.total
  } finally {
    unmappedLoading.value = false
  }
}

async function onDeleteUnmapped(id: number) {
  await deleteDeptUnmapped(id)
  ElMessage.success('已删除')
  loadUnmapped()
}

onMounted(() => {
  loadChannels()
  loadUnmapped(1)
})
</script>

<style scoped>
.unmapped-card {
  margin-top: 16px;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  align-items: center;
}

.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.status-switch {
  margin-right: 8px;
  vertical-align: middle;
}

.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
