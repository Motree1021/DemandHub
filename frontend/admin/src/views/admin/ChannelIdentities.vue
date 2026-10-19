<template>
  <div>
    <el-card shadow="never">
      <el-alert type="info" :closable="false" class="page-tip"
                title="渠道身份 = 渠道同事的一把「进门钥匙」：渠道同事免登 H5 时自动产生。把钥匙挂接到正式用户（PC 端账号）名下后，该同事渠道免登即进入正式用户账号，历史数据自动归一。" />
      <el-tabs v-model="tab" @tab-change="onTabChange">
        <!-- 待归一：钥匙还挂在渠道临时人名下，等待管理员归并 -->
        <el-tab-pane name="unbound">
          <template #label>
            待归一
            <el-badge v-if="unboundTotal" :value="unboundTotal" type="danger" class="tab-badge" />
          </template>
        </el-tab-pane>
        <el-tab-pane label="已归一" name="linked" />
        <!-- 二期：挂接/改挂审计留痕（只读） -->
        <el-tab-pane label="挂接记录" name="logs" />
      </el-tabs>

      <div v-if="tab !== 'logs'" class="toolbar">
        <el-input v-model="keyword" placeholder="渠道编号 / 渠道姓名 / 归属人" clearable class="kw"
                  @clear="onSearch" @keyup.enter="onSearch" />
        <el-button @click="onSearch">搜索</el-button>
      </div>

      <el-table v-if="tab !== 'logs'" :data="rows" v-loading="loading">
        <el-table-column label="渠道" min-width="120">
          <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
        </el-table-column>
        <el-table-column prop="channelUserId" label="渠道编号" min-width="150" />
        <el-table-column prop="channelUserName" label="渠道姓名" min-width="110" />
        <!-- 二期：同名线索（仅待归一展示；同名≠同一人，仅供核对，宁缺毋滥） -->
        <el-table-column v-if="tab === 'unbound'" label="疑似用户" min-width="180">
          <template #default="{ row }">
            <span v-if="row.suspects?.length">{{ suspectText(row) }}</span>
            <span v-else class="muted">无同名</span>
          </template>
        </el-table-column>
        <!-- 待归一显示临时账号；已归一显示归属正式用户（登录账号） -->
        <el-table-column v-if="tab === 'unbound'" label="临时账号" min-width="120">
          <template #default="{ row }">
            {{ row.ownerName }} <span class="muted">（未归一）</span>
          </template>
        </el-table-column>
        <el-table-column v-else label="归属用户" min-width="160">
          <template #default="{ row }">
            {{ row.ownerName }} <span class="muted">（{{ row.ownerAccount }}）</span>
          </template>
        </el-table-column>
        <el-table-column label="最近活跃" width="170">
          <template #default="{ row }">{{ fmtTime(row.lastSeenAt) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button v-if="tab === 'unbound'" type="primary" size="small"
                       @click="openLink(row)">挂接</el-button>
            <el-button v-else type="warning" size="small" @click="openRebind(row)">改挂</el-button>
          </template>
        </el-table-column>
        <template #empty>
          {{ tab === 'unbound' ? '没有待归一的渠道身份（渠道同事登录 H5 后才会出现）' : '暂无已归一的渠道身份' }}
        </template>
      </el-table>
      <el-pagination v-if="tab !== 'logs'" v-model:current-page="page" v-model:page-size="size" :total="total"
                     :page-sizes="[10, 20, 50]" layout="total, sizes, prev, pager, next"
                     class="pager" @size-change="onSearch" @current-change="load" />

      <!-- 二期：挂接记录（审计只读）——每次挂接/改挂都会留痕 -->
      <el-table v-if="tab === 'logs'" :data="logRows" v-loading="logLoading">
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.createdAt) }}</template>
        </el-table-column>
        <el-table-column label="动作" width="90">
          <template #default="{ row }">
            <el-tag :type="row.action === 'LINK' ? 'primary' : 'warning'" size="small">
              {{ row.action === 'LINK' ? '挂接' : '改挂' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="渠道钥匙" min-width="200">
          <template #default="{ row }">
            {{ channelLabel(row.channel) }}　{{ row.channelUserId }}
          </template>
        </el-table-column>
        <el-table-column label="归属变化" min-width="170">
          <template #default="{ row }">{{ row.fromUserName }} → {{ row.toUserName }}</template>
        </el-table-column>
        <el-table-column label="过户明细" min-width="180">
          <template #default="{ row }">
            <span v-if="row.movedCounts">{{ movedText(row.movedCounts) }}</span>
            <span v-else class="muted">只移钥匙不搬数据</span>
          </template>
        </el-table-column>
        <el-table-column prop="operatorName" label="操作人" width="100" />
        <template #empty>暂无挂接记录</template>
      </el-table>
      <el-pagination v-if="tab === 'logs'" v-model:current-page="logPage" v-model:page-size="logSize"
                     :total="logTotal" :page-sizes="[10, 20, 50]"
                     layout="total, sizes, prev, pager, next" class="pager"
                     @size-change="onLogSizeChange" @current-change="loadLogs" />
    </el-card>

    <!-- 挂接：钥匙 + 历史数据一起归到目标用户，临时账号停用 -->
    <el-dialog v-model="linkVisible" title="挂接渠道身份" width="520px">
      <el-alert type="warning" :closable="false" class="dlg-tip"
                title="挂接后：该同事渠道免登即进入所选用户账号；临时账号名下的历史数据（提报需求、评论、工时等）全部过户，临时账号停用。" />
      <!-- 二期：同名线索提示——同名≠同一人，仅辅助核对 -->
      <el-alert v-if="linkSuspects.length" type="info" :closable="false" class="dlg-tip"
                :title="`发现 ${linkSuspects.length} 个同名用户，已为您预选；同名不一定是同一人，请核对后再挂接。`" />
      <el-alert v-else-if="linkTarget" type="warning" :closable="false" class="dlg-tip"
                title="未找到同名用户，请谨慎核对所选目标。" />
      <div v-if="linkTarget" class="id-summary">
        渠道：{{ channelLabel(linkTarget.channel) }}　编号：{{ linkTarget.channelUserId }}<br>
        渠道姓名：{{ linkTarget.channelUserName }}　临时账号：{{ linkTarget.ownerName }}
      </div>
      <el-select v-model="linkUserId" filterable remote :remote-method="searchPcUsers"
                 :loading="pcUserLoading" placeholder="搜索目标用户（姓名 / 登录账号）" class="user-select">
        <el-option v-for="u in pcUserOptions" :key="u.id" :value="u.id"
                   :label="`${u.name}（${u.loginAccount}）`" />
      </el-select>
      <template #footer>
        <el-button @click="linkVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" :disabled="!linkUserId"
                   @click="submitLink">确认挂接</el-button>
      </template>
    </el-dialog>

    <!-- 改挂：只移钥匙不搬历史数据 -->
    <el-dialog v-model="rebindVisible" title="改挂渠道身份" width="520px">
      <el-alert type="warning" :closable="false" class="dlg-tip"
                title="改挂只移动渠道钥匙：历史数据留在原用户名下（已过户的数据无法再区分归属），仅渠道免登入口变更。" />
      <div v-if="rebindTarget" class="id-summary">
        渠道：{{ channelLabel(rebindTarget.channel) }}　编号：{{ rebindTarget.channelUserId }}<br>
        渠道姓名：{{ rebindTarget.channelUserName }}　当前归属：{{ rebindTarget.ownerName }}（{{ rebindTarget.ownerAccount }}）
      </div>
      <el-select v-model="rebindUserId" filterable remote :remote-method="searchPcUsers"
                 :loading="pcUserLoading" placeholder="搜索目标用户（姓名 / 登录账号）" class="user-select">
        <el-option v-for="u in pcUserOptions" :key="u.id" :value="u.id"
                   :label="`${u.name}（${u.loginAccount}）`" :disabled="u.id === rebindTarget?.ownerId" />
      </el-select>
      <template #footer>
        <el-button @click="rebindVisible = false">取消</el-button>
        <el-button type="warning" :loading="submitting" :disabled="!rebindUserId"
                   @click="submitRebind">确认改挂</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/** OneID：渠道身份独立管理页。
 * 待归一 = 钥匙挂在渠道临时人名下（管理员的治理待办，按最近活跃倒序，附同名线索辅助核对）；
 * 已归一 = 钥匙已挂到 PC 用户（OneID 用户）名下，可改挂；
 * 挂接记录 = 挂接/改挂审计留痕（只读）。
 * 二期（2026-10-18 拍板）：同名线索仅「姓名完全一致」且仅 ACTIVE 正式用户，宁缺毋滥，不自动挂接。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { channelApi, identitiesApi, usersApi } from '@/api'
import type { ChannelIdentityRow, IdentityLinkLogRow } from '@/api'
import { ApiError } from '@/api/request'

const tab = ref<'unbound' | 'linked' | 'logs'>('unbound')
const keyword = ref('')
const page = ref(1)
const size = ref(20)
const total = ref(0)
const unboundTotal = ref(0)  // 待归一总数（Tab 角标，挂接成功后联动刷新）
const rows = ref<ChannelIdentityRow[]>([])
const loading = ref(false)
const submitting = ref(false)

/** 渠道代码 → 渠道名映射（加载失败降级显示代码） */
const channelMap = ref<Record<string, string>>({})
const channelLabel = (code: string) => channelMap.value[code] ?? code

/** ISO 时间串 → 「YYYY-MM-DD HH:mm:ss」（后端出参带 T 与毫秒，直接展示太噪） */
const fmtTime = (s: string | null) => (s ? s.replace('T', ' ').slice(0, 19) : '—')

/** 疑似用户列文案：「张三（zhangsan）、张三（zhang.san）」 */
const suspectText = (row: ChannelIdentityRow) =>
  (row.suspects ?? []).map((s) => `${s.name}（${s.loginAccount ?? '—'}）`).join('、')

async function load() {
  loading.value = true
  try {
    const data = await identitiesApi.list({
      linked: tab.value === 'linked',
      keyword: keyword.value || undefined, page: page.value, size: size.value,
    })
    rows.value = data.list
    total.value = data.total
    if (tab.value === 'unbound') unboundTotal.value = data.total
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '加载失败')
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}

function onTabChange() {
  keyword.value = ''
  page.value = 1
  if (tab.value === 'logs') {
    logPage.value = 1
    loadLogs()
  } else {
    load()
  }
}

// ---- 挂接记录（二期）：挂接/改挂审计留痕，只读 ----
const logRows = ref<IdentityLinkLogRow[]>([])
const logTotal = ref(0)
const logPage = ref(1)
const logSize = ref(20)
const logLoading = ref(false)

async function loadLogs() {
  logLoading.value = true
  try {
    const data = await identitiesApi.linkLogs({ page: logPage.value, size: logSize.value })
    logRows.value = data.list
    logTotal.value = data.total
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '加载失败')
  } finally {
    logLoading.value = false
  }
}

function onLogSizeChange() {
  logPage.value = 1
  loadLogs()
}

// ---- 挂接 / 改挂共用：远程搜索 PC 用户（仅正式用户且启用中可作目标） ----
/** 下拉选项只需 id/姓名/登录账号；同名线索合并进来也满足该结构 */
type PcUserOption = { id: number; name: string; loginAccount: string | null }
const pcUserOptions = ref<PcUserOption[]>([])
const pcUserLoading = ref(false)

async function searchPcUsers(kw: string) {
  // 清空关键词时保留现有选项：挂接弹窗预选的同名线索需保持可渲染
  if (!kw) return
  pcUserLoading.value = true
  try {
    const data = await usersApi.list({ page: 1, size: 20, keyword: kw, channel: 'ACCOUNT' })
    pcUserOptions.value = data.list.filter((u) => u.status === 'ACTIVE')
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '搜索失败')
  } finally {
    pcUserLoading.value = false
  }
}

// ---- 挂接 ----
const linkVisible = ref(false)
const linkTarget = ref<ChannelIdentityRow | null>(null)
const linkUserId = ref<number | null>(null)

/** 当前挂接目标的同名线索（弹窗提示条用） */
const linkSuspects = computed(() => linkTarget.value?.suspects ?? [])

function openLink(row: ChannelIdentityRow) {
  linkTarget.value = row
  // 二期：同名线索合入选项并预选第一个——只是辅助核对，管理员仍可改选
  pcUserOptions.value = [...linkSuspects.value]
  linkUserId.value = linkSuspects.value[0]?.id ?? null
  linkVisible.value = true
}

/** 过户数据量明细：「提报需求 3 条、评论 5 条」，空 = 无业务数据 */
const movedText = (counts: Record<string, number>) =>
  Object.entries(counts).map(([label, n]) => `${label} ${n} 条`).join('、') || '无业务数据'

async function submitLink() {
  if (!linkTarget.value || !linkUserId.value) return
  const target = pcUserOptions.value.find((u) => u.id === linkUserId.value)
  const row = linkTarget.value
  // 二期：确认框带匹配依据，给管理员最后一道核对
  const suspects = row.suspects ?? []
  const basis = target && suspects.some((s) => s.id === target.id)
    ? '匹配依据：所选用户与渠道姓名同名。'
    : suspects.length
      ? '注意：所选用户与渠道姓名不同名，请再次核对。'
      : '提示：未找到同名线索，请确认所选用户无误。'
  try {
    await ElMessageBox.confirm(
      `确认把渠道身份「${row.channelUserName}（${row.channelUserId}）」挂接到「${target?.name}」名下？` +
      `临时账号「${row.ownerName}」的历史数据将全部过户并停用。${basis}`,
      '确认挂接', { confirmButtonText: '确认挂接', cancelButtonText: '取消', type: 'warning' })
  } catch { return }  // 用户取消
  submitting.value = true
  try {
    const result = await identitiesApi.link(linkUserId.value, row.id)
    linkVisible.value = false
    await ElMessageBox.alert(`挂接完成，已过户：${movedText(result.movedCounts)}`, '挂接成功',
                             { confirmButtonText: '知道了', type: 'success' })
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '挂接失败')
  } finally {
    submitting.value = false
  }
}

// ---- 改挂 ----
const rebindVisible = ref(false)
const rebindTarget = ref<ChannelIdentityRow | null>(null)
const rebindUserId = ref<number | null>(null)

function openRebind(row: ChannelIdentityRow) {
  rebindTarget.value = row
  rebindUserId.value = null
  pcUserOptions.value = []
  rebindVisible.value = true
}

async function submitRebind() {
  if (!rebindTarget.value || !rebindUserId.value) return
  submitting.value = true
  try {
    await identitiesApi.rebind(rebindTarget.value.id, rebindUserId.value)
    ElMessage.success('已改挂')
    rebindVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(e instanceof ApiError ? e.message : '改挂失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  load()
  channelApi.list()
    .then((channels) => { channelMap.value = Object.fromEntries(channels.map((c) => [c.channelCode, c.channelName])) })
    .catch(() => { /* 渠道名加载失败不阻塞主流程 */ })
})
</script>

<style scoped>
.page-tip { margin-bottom: 4px; }
.tab-badge { margin-left: 6px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
.kw { width: 280px; }
.muted { color: #909399; font-size: 12px; }
.pager { margin-top: 12px; justify-content: flex-end; }
.dlg-tip { margin-bottom: 12px; }
.id-summary { color: #606266; font-size: 13px; line-height: 1.8; margin-bottom: 12px; }
.user-select { width: 100%; }
</style>
