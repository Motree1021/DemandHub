# H5 提报页对齐原型：chat-first 重构 + 去术语化

## Context

用户反馈两个问题：
1. **术语不可理解**：当前提报页把「业务需求（Why）/用户需求（Who/What）/功能需求（How）」三层内部分类直接作为表单分区标题（ZONE_META），要求业务员工自理解、自分类、自填，认知负担过重。
2. **与原型不一致**：原型（`DemandHub_科技需求收集智能体_H5原型_v1.0.html`）是 **chat-first** 范式——顶部步骤条（表达→拆解→确认→追问→提交）、聊天气泡流为页面主体、选项 chips 引导、要素表单以实时卡片嵌在对话中、一次一题追问；当前实现是 **form-first**——五区整表平铺 + AI 助手收在底部弹层（AgentGuideSheet）。

改造目标：对齐原型 chat-first 范式；术语退居「AI 拆解结果的展示标签」并加白话注释，用户全程说人话；保留手填能力与 AI 不可用（1401）降级整表能力。后端零改动（SSE payload 已含 quickReplies/typeRecognition/granularityHint/impactHints/summary/elements，够用）。

设计决策（默认值，用户未另行指定）：
- 完全对齐原型 chat-first
- 分区名保留 + 白话注释（原型要素卡本身也显示「B 业务需求」，关键是不让用户按术语自填）
- 要素卡可点击编辑 + AI 不可用时自动降级整表

## 改动范围（仅 frontend/h5）

### 1. `src/views/report/index.vue` — 重构为对话页

页面骨架改为 flex 列布局（高 100dvh）：

```
AppLayout（保留，tabbar 不动）
├─ 草稿/错误 notice（保留现有两条 van-notice-bar）
├─ StepsBar（新组件）：表达→拆解→确认→追问→提交
├─ AgentChatPanel（聊天流，flex:1 滚动，见 §2）
├─ 底部输入栏（从 AgentGuideSheet 提取，常驻）
└─ FullFormSheet（完整表单抽屉，见 §4）+ FieldEditSheet（字段编辑弹层）
```

保留不动的逻辑（全部迁移、不改语义）：`save()` 幂等创建链（clientRequestId/sessionStorage CREATE_KEY）、`prepareAgent`、`applyAgent`（revision 校验 + flash 高亮）、`onConfirmType`、`submit`、`restoreCreation/restoreDetail/initialize/resetNewDraft`、generation 防迟到系列。

变化点：
- 删除 intro 区、zoneGroups/plainFields/extraFields 的**主视图平铺渲染**（整表移入 FullFormSheet 抽屉）
- `guideVisible`/`autoMessage` 移除；页面初始化完成即 `prepareAgent()` 建立会话（无 draftId 时先不建，首条用户消息发送时才建——保持「对话前先持久化手填」语义）
- 示例入口：EXAMPLES 保留，改为欢迎语选项 chips；`adoptExample` 改为直接调用聊天面板的 `sendMessage(text)`
- 提交成功后在聊天流内追加成功卡（需求编号），随后 `router.replace('/demand/:id')`（现有行为不变）
- 新增步骤推导 computed（供 StepsBar）：
  - 无 AI 回复 → 表达；已有拆解回复 → 拆解；判型卡展示中 → 确认；存在 quickReplies/质量缺口追问中 → 追问；`canSubmit` → 提交
- 新增 welcome 区块（聊天流顶部本地渲染，不入库）：原型欢迎语文案 + 三入口选项（大段粘贴→聚焦输入栏；看示例→示例 chips；模糊想法→发送引导语「我只有一个模糊想法」让 AI 引导）
- 1401 降级：`unavailable` 时自动展开 FullFormSheet 并提示「AI 暂不可用，可直接填写表单提交」（现有 notice 语义保留并前置）

### 2. `src/components/AgentGuideSheet.vue` → `src/components/AgentChatPanel.vue`（改名+内联化）

仅被提报页引用，可直接改名改造，无兼容负担。

- 去掉 `van-popup` 包裹、`show`/`autoMessage` props 与相关 watch；组件常驻渲染
- props 保留：`demandId/sessionId/revision/prepare`；emits 保留：`busy/complete/confirm-type`
- 新增 `defineExpose({ sendMessage(text) })` 供页面注入示例文本/入口引导语
- 保留全部状态机：messages/pending（sessionStorage 幂等）/partialReply 流式/thinking/failure/unavailable/historyGeneration/runGeneration/409 清 pending 重发/1401 降级
- `loadHistory()` 改为 onMounted + demandId/sessionId 变化时执行（原 onOpen 逻辑）
- 聊天流渲染增强（对齐原型）：
  - 消息气泡带角色头像与「需求收集智能体/我」署名
  - 判型卡 typeCard 从面板底部固定位**移入聊天流**（作为最新一条 assistant 消息的附件卡）；选项对齐原型三项：「对，是业务需求」「不是，只是日常功能需求」「我也说不清，你帮我判断」（第三项走 `confirm-type('none')` 反义路径——发一条普通消息让 AI 按模型置信度继续，不落 confirmed；实现为向输入流发送固定话术「我也说不清，你帮我判断」）
  - granularityHint/impactHints 同样改为聊天流内 banner 卡（逻辑不变，位置变化）
  - quickReplies chips 保留在输入栏上方
  - 每条带结构化 payload 的 assistant 回复后挂载 **FormSnapshotCard**（见 §3）
  - summary（canSubmit/qualityComplete 提示）保留；`canSubmit` 时追加操作 chips：「确认提交」「先保存草稿」——emit 新事件 `submit` / `save-draft` 由页面执行

### 3. 新建 `src/components/FormSnapshotCard.vue` — 要素表单实时卡

对齐原型 `formCard()`：
- props：`standard`、`form`（或 structured）、`quality: ElementStatus[]`、`fieldSources`
- 按 A/B/C/D 分区渲染：分区标题 = 现有术语 + 白话注释：
  - `A · 公共要素（基本信息）`
  - `B · 业务需求（为什么做、价值是什么）`
  - `C · 用户需求（谁用、做什么）`
  - `D · 功能需求（系统要做什么）`
- 每要素一行：名称 + 值摘要（超长省略）+ 状态 pill（已填/待补充，依据 quality 中 OK/VAGUE vs MISSING/SKIP）；system 字段（A4/A5）不渲染
- 点击字段行 → emit(`edit-field`, field)，页面打开 FieldEditSheet
- 无 standard 或草稿未建时不渲染

### 4. 手填编辑能力

- 新建 `src/components/FieldEditSheet.vue`：van-popup 包一个 `StandardField` + 确认按钮；复用 `manualEdit`/`writeUserField`（标 source=user、dirty、demandTypeCode 切换清 ext 逻辑不变）
- 新建 `src/components/FullFormSheet.vue`（或保留在 index.vue 内的 van-popup）：迁移现有五区整表 + 质量卡 + E 区状态卡（字段来源/变更留痕），zone 标题同步加白话注释；入口为聊天面板工具区「查看/填写完整表单」按钮 + AI 降级时自动展开

### 5. `src/components/StepsBar.vue` — 步骤条

- props：`step: 0..4`（由页面推导）；纯展示组件，五段圆点+连线样式对齐原型（当前步高亮、已过步绿色）

### 6. 测试迁移（tests/）

- `agent-sheet.test.ts` → 改名 `agent-panel.test.ts`：挂载 AgentChatPanel（去 PopupStub/show prop），断言点全部保留（EOF 重试幂等、409 清 pending、切草稿不回写、1401 降级、迟到会话防回写）；`show` 相关用例改为 demandId/sessionId 切换语义
- `guide-p4.test.ts`：判型卡/粒度/影响提示断言目标从弹层固定位改为聊天流内卡，其余不变；新增「说不清帮我判断」第三选项用例
- `report.test.ts`：初始化/恢复/保存幂等/迟到草稿防覆盖等核心用例保留；涉及 guideVisible 弹层的断言改为内联面板；新增欢迎语三入口渲染用例
- 新增 `form-snapshot.test.ts`：分区注释渲染、已填/待补充 pill 状态、点击 emit edit-field、system 字段不渲染
- 新增 `steps-bar.test.ts`：五态渲染与当前步高亮

### 不做的事
- 后端零改动；路由/tabbar/admin/mine/detail 页不动
- 原型的「修改弹窗 maskModify」「草稿弹窗 maskDraft」仅演示用途，不照搬（现有保存/冲突流程已覆盖语义）
- 要素 key 标注（原型注明"生产环境隐藏"）不渲染

## 验证

1. `cd frontend/h5 && npm run typecheck && npm run test && npm run build` 三绿
2. 本地链路（8000 Mock Ark + 5174）：签 ticket 后人工回归——
   - 欢迎语三入口 → 采用示例一 → 聊天流拆解 + 要素实时卡（白话注释分区）→ 判型卡三选项 → 追问 chips → canSubmit 操作 chips → 提交成功卡含编号
   - 对话改 B1 → 影响提示 banner + 要素卡值更新
   - 要素卡点击字段 → FieldEditSheet 手改 → source=user、dirty → 保存草稿
3. 1401 降级：停 ark_mock(8188) → 发送消息 → 面板提示降级 + FullFormSheet 自动展开可手填提交
4. 复跑 `scripts/p5_scenarios.ps1` 确认后端链路无回归（后端未动，预期全过）
