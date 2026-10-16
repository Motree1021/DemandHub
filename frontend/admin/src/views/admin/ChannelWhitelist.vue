<template>
  <div>
    <!-- 渠道控制条 -->
    <el-card shadow="never">
      <div class="channel-row">
        <div class="channel-name">
          {{ channel?.channelName || '创金零售小程序' }}
          <el-tag size="small" effect="plain">{{ channelCode }}</el-tag>
        </div>
        <div class="ctl-item">
          <span class="ctl-label">白名单校验</span>
          <el-switch :model-value="whitelistEnabled" :before-change="onSwitchBefore" :loading="switching" />
          <span :class="['switch-state', whitelistEnabled ? 'on' : 'off']">
            {{ whitelistEnabled ? '已开启' : '已关闭' }}
          </span>
        </div>
        <div class="ctl-item">
          <span class="ctl-label">拦截页联系引导</span>
          <span class="contact-text" :title="whitelistContact || ''">{{ whitelistContact || '未配置' }}</span>
          <el-button size="small" @click="contactDialog = true">编辑</el-button>
        </div>
      </div>
      <el-alert v-if="!whitelistEnabled" type="warning" :closable="false" class="off-tip"
                title="白名单校验已关闭：当前所有渠道用户均可进入 H5（自动建档）。开启后仅白名单内用户可进入。" />
    </el-card>

    <!-- 统计 -->
    <div class="stat-row">
      <el-card shadow="never" class="stat-card"><div class="num blue">{{ stats.enabled }}</div><div class="lbl">已启用</div></el-card>
      <el-card shadow="never" class="stat-card"><div class="num orange">{{ stats.disabled }}</div><div class="lbl">已停用</div></el-card>
      <el-card shadow="never" class="stat-card"><div class="num gray">{{ pending.length }}</div><div class="lbl">待登记老用户</div></el-card>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <!-- 白名单列表 -->
        <el-tab-pane label="白名单" name="list">
          <div class="toolbar">
            <el-input v-model="keyword" placeholder="搜索企微ID / 姓名" clearable style="width: 260px"
                      @clear="onSearch" @keyup.enter="onSearch" />
            <div class="toolbar-right">
              <el-button @click="openBatch">批量添加</el-button>
              <el-button type="primary" @click="addDialog = true">+ 添加白名单</el-button>
            </div>
          </div>
          <el-table :data="entries" v-loading="loadingList">
            <el-table-column prop="channelUserId" label="企微ID" min-width="150" />
            <el-table-column label="姓名" min-width="100">
              <template #default="{ row }">{{ row.displayName || '—' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'">
                  {{ row.status === 'ENABLED' ? '已启用' : '已停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="最近登录" width="170">
              <template #default="{ row }">{{ row.lastLoginAt || '—（从未登录）' }}</template>
            </el-table-column>
            <el-table-column prop="createdByName" label="登记人" width="100" />
            <el-table-column prop="createdAt" label="登记时间" width="170" />
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button link :type="row.status === 'ENABLED' ? 'warning' : 'success'" @click="onToggleEntry(row)">
                  {{ row.status === 'ENABLED' ? '停用' : '启用' }}
                </el-button>
                <el-button link type="danger" @click="onRemove(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination v-model:current-page="page" v-model:page-size="size" :total="total"
                         :page-sizes="[10, 20, 50, 100]" layout="total, sizes, prev, pager, next, jumper"
                         class="pager" @size-change="onSearch" @current-change="loadList" />
        </el-tab-pane>

        <!-- 待登记渠道用户 -->
        <el-tab-pane name="pending">
          <template #label>
            待登记渠道用户
            <el-badge v-if="pending.length" :value="pending.length" type="danger" class="tab-badge" />
          </template>
          <el-alert type="warning" :closable="false" class="pending-tip">
            <template #title>
              以下用户在系统中已有档案（白名单功能上线前自动建档），但尚未加入白名单。<b>开启白名单校验后，这些用户将被拦截</b>，请逐一确认后点击「加入白名单」。
            </template>
          </el-alert>
          <el-table :data="pending" v-loading="loadingPending">
            <el-table-column prop="wecomUserid" label="企微ID" min-width="150" />
            <el-table-column prop="name" label="姓名" min-width="100" />
            <el-table-column label="部门" min-width="140">
              <template #default="{ row }">{{ row.deptName || '未匹配部门' }}</template>
            </el-table-column>
            <el-table-column label="最近登录" width="170">
              <template #default="{ row }">{{ row.lastLoginAt || '—' }}</template>
            </el-table-column>
            <el-table-column prop="demandCount" label="提报需求数" width="100" />
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" size="small" :loading="row._adding" @click="onQuickAdd(row)">加入白名单</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 操作留痕 -->
        <el-tab-pane label="操作留痕" name="logs">
          <el-table :data="logs" v-loading="loadingLogs">
            <el-table-column prop="createdAt" label="时间" width="170" />
            <el-table-column prop="operatorName" label="操作人" width="110" />
            <el-table-column label="动作" width="130">
              <template #default="{ row }">
                <span :class="['action-label', row.action]">{{ ACTION_LABELS[row.action] || row.action }}</span>
              </template>
            </el-table-column>
            <el-table-column label="对象" min-width="140">
              <template #default="{ row }">{{ row.channelUserId || '—' }}</template>
            </el-table-column>
            <el-table-column label="详情" min-width="220" show-overflow-tooltip>
              <template #default="{ row }">{{ row.detail || '—' }}</template>
            </el-table-column>
          </el-table>
          <el-pagination v-model:current-page="logPage" :page-size="20" :total="logTotal"
                         layout="total, prev, pager, next" class="pager" @current-change="loadLogs" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- 添加白名单 -->
    <el-dialog v-model="addDialog" title="添加白名单" width="440px" @closed="resetAdd">
      <el-form label-position="top">
        <el-form-item label="企微ID" required>
          <el-input v-model="addForm.channelUserId" placeholder="请输入渠道侧企微用户ID，如 zhang.wei01" />
          <div class="form-tip">从渠道方（创金零售）提供的名单中获取，区分大小写</div>
        </el-form-item>
        <el-form-item label="姓名（选填）">
          <el-input v-model="addForm.displayName" placeholder="便于日后核对，如 张伟" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" :disabled="!addForm.channelUserId.trim()" @click="onAdd">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- 批量添加 -->
    <el-dialog v-model="batchDialog" title="批量添加白名单" width="560px" @closed="resetBatch">
      <el-form label-position="top">
        <el-form-item label="企微ID 名单" required>
          <el-input v-model="batchText" type="textarea" :rows="6" style="font-family: Consolas, monospace"
                    :placeholder="'每行一个企微ID，可从 Excel 整列直接粘贴\n如需同时登记姓名，用逗号 / Tab / 空格分隔：\nsun.qian07,孙倩\nzhou.jie08 周杰'" />
          <div class="form-tip">空行自动忽略；与现有白名单重复的自动跳过；粘贴后先「解析」再确认</div>
        </el-form-item>
      </el-form>
      <template v-if="batchParsed">
        <div class="parse-summary">
          解析结果：<b class="ok-text">可添加 {{ batchOk.length }} 条</b> · 重复跳过 {{ batchDup.length }} 条 · 格式无效 {{ batchBad.length }} 条
        </div>
        <div v-if="batchOk.length" class="parse-box ok-box">
          <div v-for="item in batchOk" :key="item">{{ item }}</div>
        </div>
        <div v-if="batchDup.length" class="parse-box dup-box">重复（粘贴内容自身重复）：{{ batchDup.join('、') }}（服务端将二次校验已存在项）</div>
        <div v-if="batchBad.length" class="parse-box bad-box">
          <div>格式无效（企微ID仅允许字母/数字/._-，≤64字符）：</div>
          <div v-for="item in batchBad" :key="item">{{ item }}</div>
        </div>
      </template>
      <template #footer>
        <el-button @click="batchDialog = false">取消</el-button>
        <el-button @click="parseBatch">解析</el-button>
        <el-button v-if="batchParsed && batchOkEntries.length" type="primary" :loading="adding" @click="onBatchCommit">
          确认添加 {{ batchOkEntries.length }} 条
        </el-button>
      </template>
    </el-dialog>

    <!-- 联系引导编辑 -->
    <el-dialog v-model="contactDialog" title="编辑拦截页联系引导" width="440px" @closed="contactDraft = whitelistContact">
      <el-input v-model="contactDraft" type="textarea" :rows="3" maxlength="255" show-word-limit
                placeholder="如：请联系科技部需求管理员 张敏 开通访问权限（企业微信直接搜索）" />
      <div class="form-tip">展示在被拦截用户看到的 H5 页面上，建议包含可触达的联系人或渠道；清空则不展示联系卡片</div>
      <template #footer>
        <el-button @click="contactDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="onSaveContact">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, ref } from 'vue'
import { channelApi, whitelistApi } from '@/api'
import type { ChannelRow, WhitelistEntry, WhitelistLogRow, WhitelistPendingRow } from '@/api'

const ACTION_LABELS: Record<string, string> = {
  ADD: '添加', ENABLE: '启用', DISABLE: '停用', REMOVE: '移除',
  SWITCH_ON: '开启全局开关', SWITCH_OFF: '关闭全局开关', UPDATE_CONTACT: '修改联系引导',
}

const channel = ref<ChannelRow>()
const channelCode = ref('CHUANGJIN_LS')
const whitelistEnabled = ref(false)
const whitelistContact = ref('')
const switching = ref(false)

const stats = ref({ enabled: 0, disabled: 0 })
const activeTab = ref('list')

const entries = ref<WhitelistEntry[]>([])
const keyword = ref('')
const page = ref(1)
const size = ref(20)
const total = ref(0)
const loadingList = ref(false)

const pending = ref<(WhitelistPendingRow & { _adding?: boolean })[]>([])
const loadingPending = ref(false)

const logs = ref<WhitelistLogRow[]>([])
const logPage = ref(1)
const logTotal = ref(0)
const loadingLogs = ref(false)

const adding = ref(false)
const addDialog = ref(false)
const addForm = ref({ channelUserId: '', displayName: '' })

const batchDialog = ref(false)
const batchText = ref('')
const batchParsed = ref(false)
const batchOk = ref<string[]>([])
const batchOkEntries = ref<{ channelUserId: string; displayName?: string }[]>([])
const batchDup = ref<string[]>([])
const batchBad = ref<string[]>([])

const contactDialog = ref(false)
const contactDraft = ref('')

async function loadChannel() {
  const list = await channelApi.list()
  channel.value = list.find(c => c.channelCode === 'CHUANGJIN_LS') || list[0]
  if (channel.value) {
    channelCode.value = channel.value.channelCode
    whitelistEnabled.value = channel.value.whitelistEnabled
    whitelistContact.value = channel.value.whitelistContact || ''
    contactDraft.value = whitelistContact.value
  }
}

async function loadList() {
  loadingList.value = true
  try {
    const data = await whitelistApi.list(channelCode.value, {
      page: page.value, size: size.value, keyword: keyword.value.trim() || undefined,
    })
    entries.value = data.list
    total.value = data.total
    stats.value = data.stats
  } finally {
    loadingList.value = false
  }
}

async function loadPending() {
  loadingPending.value = true
  try {
    pending.value = await whitelistApi.pending(channelCode.value)
  } finally {
    loadingPending.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const data = await whitelistApi.logs(channelCode.value, { page: logPage.value, size: 20 })
    logs.value = data.list
    logTotal.value = data.total
  } finally {
    loadingLogs.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadList(), loadPending(), loadLogs()])
}

function onSearch() {
  page.value = 1
  loadList()
}

async function onSwitchBefore(): Promise<boolean> {
  const enabling = !whitelistEnabled.value
  switching.value = true
  try {
    await ElMessageBox.confirm(
      enabling
        ? '开启后，仅白名单内的渠道用户可以进入 H5。未登记用户（含白名单功能上线前已自动建档的老用户）将被拦截，并看到「非白名单用户，暂不支持访问」页面。确认开启？'
        : '关闭后，所有渠道用户均可进入 H5（白名单校验停用，自动建档）。仅在白名单配置异常导致大面积误拦等紧急情况下使用。确认关闭？',
      enabling ? '开启白名单校验' : '关闭白名单校验',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' })
  } catch {
    return false
  } finally {
    switching.value = false
  }
  const result = await whitelistApi.updateConfig(channelCode.value, { whitelistEnabled: enabling })
  whitelistEnabled.value = result.whitelistEnabled
  ElMessage.success(enabling ? '已开启白名单校验' : '已关闭白名单校验')
  loadLogs()
  return true
}

async function onToggleEntry(row: WhitelistEntry) {
  const next = row.status === 'ENABLED' ? 'DISABLED' : 'ENABLED'
  await whitelistApi.updateStatus(row.id, next)
  ElMessage.success(next === 'DISABLED' ? '已停用，该用户将无法进入 H5' : '已启用')
  await Promise.all([loadList(), loadLogs()])
}

async function onRemove(row: WhitelistEntry) {
  await ElMessageBox.confirm(
    `确认将「${row.channelUserId}${row.displayName ? '（' + row.displayName + '）' : ''}」移出白名单？移除后该用户无法进入 H5（已有系统档案保留，可随时重新加入）。`,
    '移除确认', { type: 'warning', confirmButtonText: '确认移除', cancelButtonText: '取消' })
  await whitelistApi.remove(row.id)
  ElMessage.success('已移除')
  await Promise.all([loadList(), loadLogs()])
}

async function onQuickAdd(row: WhitelistPendingRow & { _adding?: boolean }) {
  row._adding = true
  try {
    await whitelistApi.add(channelCode.value, { channelUserId: row.wecomUserid, displayName: row.name })
    ElMessage.success(`已将「${row.name}」加入白名单`)
    await Promise.all([loadList(), loadPending(), loadLogs()])
  } finally {
    row._adding = false
  }
}

function resetAdd() {
  addForm.value = { channelUserId: '', displayName: '' }
}

async function onAdd() {
  adding.value = true
  try {
    await whitelistApi.add(channelCode.value, {
      channelUserId: addForm.value.channelUserId.trim(),
      displayName: addForm.value.displayName.trim() || undefined,
    })
    ElMessage.success('已添加')
    addDialog.value = false
    await Promise.all([loadList(), loadLogs()])
  } finally {
    adding.value = false
  }
}

function openBatch() {
  batchDialog.value = true
}

function resetBatch() {
  batchText.value = ''
  batchParsed.value = false
  batchOk.value = []
  batchOkEntries.value = []
  batchDup.value = []
  batchBad.value = []
}

function parseBatch() {
  const ok: string[] = []
  const okEntries: { channelUserId: string; displayName?: string }[] = []
  const dup: string[] = []
  const bad: string[] = []
  const seen = new Set<string>()
  for (const line of batchText.value.split(/\r?\n/)) {
    const t = line.trim()
    if (!t) continue
    let id = t
    let name = ''
    const byComma = t.split(/[,，\t]/).map(s => s.trim()).filter(Boolean)
    if (byComma.length > 1) {
      id = byComma[0]
      name = byComma[1]
    } else if (/\s/.test(t)) {
      const parts = t.split(/\s+/)
      id = parts[0]
      name = parts.slice(1).join(' ')
    }
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(id)) { bad.push(t); continue }
    const key = id.toLowerCase()
    if (seen.has(key)) { dup.push(id); continue }
    seen.add(key)
    ok.push(name ? `${id}（${name}）` : id)
    okEntries.push({ channelUserId: id, ...(name ? { displayName: name } : {}) })
  }
  batchOk.value = ok
  batchOkEntries.value = okEntries
  batchDup.value = dup
  batchBad.value = bad
  batchParsed.value = true
}

async function onBatchCommit() {
  adding.value = true
  try {
    const result = await whitelistApi.addBatch(channelCode.value, batchOkEntries.value)
    const parts = [`成功添加 ${result.added} 条`]
    if (result.duplicated.length) parts.push(`重复跳过 ${result.duplicated.length} 条（${result.duplicated.join('、')}）`)
    if (result.invalid.length) parts.push(`格式无效 ${result.invalid.length} 条`)
    ElMessage.success(parts.join('；'))
    batchDialog.value = false
    await Promise.all([loadList(), loadPending(), loadLogs()])
  } finally {
    adding.value = false
  }
}

async function onSaveContact() {
  adding.value = true
  try {
    const result = await whitelistApi.updateConfig(channelCode.value, { whitelistContact: contactDraft.value.trim() })
    whitelistContact.value = result.whitelistContact || ''
    ElMessage.success('已保存')
    contactDialog.value = false
    loadLogs()
  } finally {
    adding.value = false
  }
}

onMounted(async () => {
  await loadChannel()
  await refreshAll()
})
</script>

<style scoped>
.channel-row { display: flex; align-items: center; gap: 28px; flex-wrap: wrap; }
.channel-name { font-weight: 600; font-size: 15px; display: flex; align-items: center; gap: 8px; }
.ctl-item { display: flex; align-items: center; gap: 10px; }
.ctl-label { color: #606266; font-size: 13px; }
.switch-state { font-size: 13px; font-weight: 600; }
.switch-state.on { color: #409eff; }
.switch-state.off { color: #909399; }
.contact-text { font-size: 13px; color: #606266; background: #f5f7fa; border-radius: 4px; padding: 5px 10px; max-width: 340px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.off-tip { margin-top: 12px; }
.stat-row { display: flex; gap: 16px; margin: 16px 0; }
.stat-card { flex: 1; }
.stat-card .num { font-size: 26px; font-weight: 700; }
.stat-card .lbl { font-size: 13px; color: #909399; margin-top: 4px; }
.num.blue { color: #409eff; }
.num.orange { color: #e6a23c; }
.num.gray { color: #606266; }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 12px; gap: 12px; }
.toolbar-right { display: flex; gap: 10px; }
.pager { margin-top: 12px; justify-content: flex-end; }
.tab-badge { margin-left: 6px; vertical-align: 2px; }
.pending-tip { margin-bottom: 12px; }
.form-tip { font-size: 12px; color: #909399; margin-top: 5px; }
.action-label.SWITCH_ON, .action-label.ENABLE { color: #409eff; }
.action-label.SWITCH_OFF, .action-label.DISABLE { color: #e6a23c; }
.action-label.REMOVE { color: #f56c6c; }
.parse-summary { font-size: 13px; margin-bottom: 8px; }
.ok-text { color: #67c23a; }
.parse-box { font-size: 12.5px; border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; line-height: 1.8; max-height: 140px; overflow-y: auto; }
.ok-box { color: #67c23a; background: #f0f9eb; }
.dup-box { color: #909399; background: #f4f4f5; }
.bad-box { color: #f56c6c; background: #fef0f0; }
</style>
