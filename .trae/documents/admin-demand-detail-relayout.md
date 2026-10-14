# 管理后台需求详情页重排（BA/产品经理审查视角）

## Context

当前管理后台【需求详情】页（`frontend/admin/src/views/demand/DemandDetail.vue`）是"信息卡 + 左右双栏散卡"布局：A 区要素混在 el-descriptions 里、B/C/D 要素只显示非空行、质量计数独立成卡、处理进度占右栏。BA/产品经理审查需求时要来回翻找，不直观。

按用户拍板重排为"审查动线"布局：**A·公共要素（横向）→ 需求概述（横向）→ 左：B/C/D 要素表单（x/27 到位）+ 右：AI 对话回放 → 底部 tabs（方案/沟通记录/工时/关联/处理进度）**。

### 已拍板口径
1. **判型置灰=向下兼容**：业务需求→B/C/D 全亮；用户需求→B 灰、C/D 亮；功能需求→B/C 灰、D 亮。判型取 `ext.typeRecognition`（confirmed 优先，否则取置信度最高层）；无判型（含物料/培训）不置灰。
2. **D9 建议方案不参与质量评估**：改后端统一口径，质量计数从 x/28 变 x/27（A4/A5 system 已跳过，D9 再跳过）。
3. **物料/培训需求**：不显示 B/C/D 要素区块（A 区+概述+回放+tabs 保留）。

### 关键现状（调研结论）
- 详情接口 `GET /demand/{id}` 已返回五件套 `{demand, quality, standard, messages, attachments}`，**无需新增后端接口**。
- 现有可复用块：`blocks/OverviewCard.vue`（四段式概述+底稿原文）、`blocks/ElementsCard.vue`（五区分组渲染逻辑）、`blocks/ChatReplayCard.vue`（回放）、`blocks/AttachmentsCard.vue`；工具函数 `utils/demand.ts`（ZONE_TITLES/readField/displayValue/allFields）。
- 质量标准：`standard.elements` 30 项（A8/B7/C6/D9 含 proposedSolution），`quality: ElementStatus[{key,label,status(OK/VAGUE/MISSING),note}]`。
- 后端质量评估入口 `server/app/standards/rules.py` `assess()`（L167-205），目前只跳 `field.system`（L171）。

## 改动清单

### 一、后端（小改，统一 27 口径）
1. `server/app/standards/schema.py`：StandardField 增加 `assessed: bool = True` 属性。
2. `server/app/standards/tech.yaml`：`proposedSolution`（D9，L396-402）标注 `assessed: false`。
3. `server/app/standards/rules.py` `assess()`：跳过条件改为 `if field.system or not field.assessed: continue`。
4. 检查同步点：`app/agent/policy.py` `complete_elements`（对话中要素状态）与 `app/services/export.py` 完备度表，若也遍历 standard.elements 需同样跳过 `assessed: false`。
5. 单测同步：`tests/test_standards_five_zones.py`（要素数量/评估计数断言 28→27）、`tests/test_standards_rules.py`、涉及 quality 长度断言的用例（`test_api_p3.py` 等），并新增一条"D9 有值也不进 quality"断言。

### 二、前端（frontend/admin）

**1. `views/demand/DemandDetail.vue` 模板重排**（脚本动作分发/弹窗逻辑不动）：
- **头部卡**：保留 demandNo + StatusTag + UrgencyTag + 操作按钮区（availableActions 驱动不变）；新增两个徽标——`ext.mode.level==='light'` 显示「轻量提报」info tag；判型徽标（业务/用户/功能需求，confirmed 实心 / AI 判空心）。删除现有 h3 标题与 el-descriptions 信息卡（内容由 A 区表单承接）。
- **打回 alert**：原位保留。
- **A · 公共要素（横向表单卡）**：新组件 `blocks/CommonZoneCard.vue`。取 `standard.elements` 中 `zone==='A'` 的 8 个字段，横向栅格（el-row/el-col，短字段 3 栏、title/content 独占一行），每格 label + 值（readField/displayValue 复用）+ 质量状态点（quality 按 key join，A4/A5 无状态不显示点）。无 standard（轻量/非科技）时降级为旧 descriptions 简表。
- **需求概述（横向卡）**：现有 `OverviewCard` 从双栏左列移出，整行放置。
- **中部双栏** `el-row`：
  - 左（lg=15）：**需求要素表单**——改造 `blocks/ElementsCard.vue`：
    - header：「需求要素」+ `x/27 项到位`（quality 中 OK 数/总数，quality 为空时显示 0/27 并提示"提交后生成评估"）；
    - B/C/D 三区竖排全量渲染（含空值行，空值显示淡色"未填写"），每行 label + 值 + 状态胶囊（到位 success/模糊 warning/缺失 info）；
    - 置灰：按判型计算灰区（见下），灰区整区半透明 + 区标题旁注"不参与本层级评估"；D9 行恒灰 + 注"选填·不参与评估"；
    - 仅 `demandTypeCode==='TECH' && standard` 时渲染，否则不显示。
  - 右（lg=9）：`ChatReplayCard`（标题改「AI 对话回放（n 条）」，n=messages.length）→ `AttachmentsCard` → `ExtInfoCard`。
- **底部 tabs 卡**：现有 4 个 tab 保留，新增第 5 个「处理进度」tab：现右栏 el-timeline 整块搬入（数据源 flow.transitions 不变），`QualityCard` 独立卡删除（计数已并入要素表单 header）。

**2. `utils/demand.ts` 新增纯函数**（便于单测）：
```ts
// 判型置灰（向下兼容）：返回灰区集合
grayZones(typeRecognition: unknown): Set<'B'|'C'>
// 'business'→∅  'user'→{B}  'function'→{B,C}  无判型→∅
```
组件内本地定义 `TypeRecognition` 接口（confirmed + business/user/function 置信度），不改全局 DemandRow 类型。

**3. 前端测试**（frontend/admin vitest）：
- `tests/demand-gray.test.ts`（新）：grayZones 纯函数三判型 + 空判型；
- 布局冒烟：可选，若现有无 DemandDetail 测试则补一个挂载测试（mock demandApi/flowApi，断言 A 区卡、概述卡、要素表单、5 个 tab 存在；物料需求不渲染要素表单）。

## 不做的事
- 不改状态机动作、面板（方案/沟通/工时/关联）内部逻辑；
- 不动 H5（其质量计数随后端 assess 自动变 27，无需改码）；
- 不加字段来源（user/agent）标记（用户未要求）。

## 验证
1. 后端：`uv run pytest tests/test_standards_five_zones.py tests/test_standards_rules.py` + `uv run ruff check app tests`（测试库未启动时至少跑不依赖 DB 的 standards 纯单测）。
2. 前端：`npm run typecheck && npm run test && npm run build`（frontend/admin）。
3. 手工核对（启动本地服务后）：科技需求（三种判型各一）检查置灰与 x/27；物料需求确认无要素区块；处理进度 tab 时间线正常；状态机操作按钮仍可用。
