# DemandHub 科技需求收集智能体 · 开发计划 v1.0

> 供 Trae 执行的任务书。目标：将现有 Python 栈 MVP 的科技需求收集模块，升级为符合《科技需求收集智能体 PRD v1.3》设计的分层需求要素收集智能体。
> 本地开发环境：无 Docker，直连本机 MySQL 3307 实例（demandhub 库 / root / Motree_1021），见 `server/.env`。

---

## 0. 必读文档（执行前先读，作为唯一设计口径）

| 文档 | 用途 |
|---|---|
| `DemandHub_科技需求收集智能体_BRD_v1.0.md`（内容 v1.3） | 业务规则 BR-T11~T13、预算撤除后的接缝说明 |
| `DemandHub_科技需求收集智能体_PRD_v1.0.md`（内容 v1.3） | **§4 标准五区表单（A1–A8/B1–B7/C1–C6/D1–D8/E1–E8）、§4.3 判型信号、§5 功能需求详述、§7 数据模型、§11 预算/IRB 接缝、§12 JSON Schema** |
| `DemandHub_科技需求收集智能体_概念模型与数据库设计_v1.0.md`（内容 v1.1） | **§2 决策 D1–D8、§4 逻辑模型、§5 DDL（可直接执行）、§6 迁移策略、§7 接缝** |
| `DemandHub_科技需求收集智能体_H5原型_v1.0.html` | 前端交互高保真参考（含"一段话示例"入口；预算相关交互已撤除） |
| `server/app/standards/tech.yaml` | 现状六要素标准（待升级为五区表单） |

---

## 0.1 与《架构演进路线 v1.0》的一致性说明

**阶段定位**：本计划属于演进路线 **V1.x「H5 提报体验优化」阶段的收集段能力增强**（V1.x+）。演进路线原文表述为"服务端能力已就绪，本阶段只优化前端呈现与引导"；本计划在此基础上扩展了**服务端能力**（五区标准 YAML、三层判型、大段拆解、修改留痕表），这些均属 BRD/PRD 已定稿需求，符合"按需建设"原则，但**不改变演进路线的阶段归属**——仍属于收集段（V1 范围内），不涉及 V2 流转/权限、V3 运营、V4 拆分。

**架构一致性**：全程保持 Python 模块化单体形态，只扩展 `server/` 内部既有分层（standards / services / api / agent），不拆服务、不引入新中间件（仅 MySQL）、不触碰渠道适配层与 Java 侧；数据边界守住（demandhub 库独立于 Java 库）、需求编号仍由 `demand_no_seq` 发放、每阶段以既有 e2e（`scripts/e2e_mvp.py`）全绿为门禁。

**表关系说明（重要）**：本计划 P0 新建的 `demand_change_log`（**要素修改留痕**，服务 FR-06 对话中修改需求）与演进路线 V2 翻译项 `demand_transition_log`（**状态流转日志**，服务 12 态状态机）是**职责不同的两张表**，不冲突、不合并。概念模型 §2 D2 已说明 change_log 为 V2 流转日志"立范式"（同样的记录风格），V2 阶段按蓝本另行新增 transition_log。

**明确不实现项**（演进路线 V1.x 中有、但依赖后续阶段或未触发条件的项）：
- "关键节点告知"（受理/验收通知）——依赖 V3 通知中心，本计划不做；
- "语音输入引导"——演进路线标注零开发（复用手机输入法语音转文字），仅补引导文案，见 P4 第 8 项；
- 实例切分（BR-T11）落库流程——V2 触发条件未写明前不强做，仅 P0 预置 split_from_id / split_group_id 列（接缝），一期可仅打标 `ext.pendingSplits`；
- 预算/IRB——一期撤除，仅留 B5–B8 位接缝（PRD §11）。

---

## 1. 现状基线（已具备，勿重复开发）

### 1.1 后端（`server/`，FastAPI + SQLAlchemy + Alembic，Python 3.12/uv）
- `app/agent/`：`guide.py`（对话编排）、`policy.py`（纯函数：merge_structured / complete_elements / inherit_and_count / pick_follow_up / reply_for / user_said_skip）、`llm_client.py`、`schemas.py`（ModelOutput / ElementStatus）
- `app/standards/`：`loader.py`（YAML 加载）、`rules.py`（assess/blank/filter_form/schema_errors/set_value）、`schema.py`（Standard 模型）、`tech.yaml`（六要素 + ask_l1/l2 + ok_when + vague_hint）
- `app/api/`：agent / demand / auth / admin / standards / health
- `app/services/`：demand_service / session_service / user_service / demand_no / export
- `app/db/models.py`：6 表（dh_user / prompt_version / demand / demand_no_seq / agent_session / agent_message）
- 测试基线：`uv run pytest` 123 passed；`uv run ruff check app tests alembic` 通过

### 1.2 前端 H5（`frontend/h5/`，Vue3 + Vant + Pinia + Vite + vitest）
- `views/demand/detail.vue`（需求详情/表单）、`views/mine/index.vue`（我的需求）
- `components/AgentGuideSheet.vue`（Agent 对话引导面板）、`StandardField.vue`（标准字段渲染）、`QualityList.vue`（判质清单）
- `api/agent.ts` / `demand.ts` / `sse.ts`（SSE 对话流）
- 已有：对话引导、判质清单、标准字段表单、SSE 流式交互

### 1.3 差距（本次开发要做的）
| 维度 | 现状 | 目标（PRD v1.3） |
|---|---|---|
| 标准表单 | 六要素（title/type/content/subtype/场景/验收/价值） | 五区 30 要素（A/B/C/D/E 区） |
| 需求判型 | 仅子类枚举（SYS_DEV 等） | 业务/用户/功能三层识别 + 置信度展示 + 用户确认/改判 |
| 大段拆解 | content 原样入库存 | 拆解为各区要素（elements JSON）+ A8 原文保真并存 |
| 粒度治理 | 无 | BR-T13：目标级分解、字段级补全，收敛标准=可验证/可追踪/可独立受理 |
| 修改留痕 | revision 计数 | demand_change_log 表（要素级 old/new） |
| 草稿续报 | status=DRAFT | 会话内续报 + 示例引导 + 修改对话 |
| 预算/IRB | 无 | **一期不做**，B5–B8 位预留接缝（PRD §11） |

---

## 2. 分阶段任务

### P0 数据库迁移（对齐概念模型 §5，DDL 已定稿）

**目标**：`demand` 表新增要素承载列 + 新建变更留痕表；零破坏现有列。

**执行**：
1. 读 `server/alembic/versions/0001_init.py` 与 `server/app/db/models.py`，新增迁移 `0002_elements_change_log.py`，内容：
   - `ALTER TABLE demand ADD COLUMN elements JSON NULL COMMENT '五区要素值(A/B/C/D)' AFTER content;`
   - `ADD COLUMN split_from_id BIGINT NULL COMMENT '实例切分来源需求id(BR-T11)' ; ADD COLUMN split_group_id CHAR(36) NULL COMMENT '同源拆分批次UUID';`
   - 索引：`ix_demand_split_group(split_group_id)`、`ix_demand_split_from(split_from_id)`；外键 `fk_demand_split_from → demand.id`
   - `CREATE TABLE demand_change_log`（字段：id PK / demand_id FK / field_key VARCHAR(64) / old_value JSON / new_value JSON / source VARCHAR(16) / changed_by BIGINT / created_at DATETIME(3)；索引 `ix_change_demand_time(demand_id, created_at)`）
2. 同步更新 `models.py`：`Demand.elements / split_from_id / split_group_id`；新增 `DemandChangeLog` 模型
3. `elements` 一期与 `ext` 双写兼容一版（概念模型 §6 迁移策略：新写入 elements、ext 兼容）
4. 预算/IRB 字段**不建**（PRD §11 接缝，恢复时零 DDL）

**验收**：
- `uv run alembic upgrade head` 在 3307 的 demandhub 执行成功（当前已 stamp 到 0001，执行后 head 为 0002）
- `SHOW COLUMNS FROM demand` 含 elements/split_from_id/split_group_id；`SHOW TABLES` 含 demand_change_log
- `uv run pytest` 仍 123 passed（回归无破坏）

---

### P1 标准 YAML 升级：六要素 → 五区 30 要素

**目标**：`server/app/standards/tech.yaml` 升级为 PRD §4 五区表单，保留现有 YAML 驱动机制（loader/rules/schema 不改或最小改）。

**执行**：
1. 按 PRD §4.2.1–4.2.4 重建 `tech.yaml` elements：
   - **A 区（公共，必填为主）**：A1 title / A2 demandTypeCode / A3 techSubtype / A6 urgency（enum 校验沿用 models 枚举） / A7 expectDeliveryAt（date，可空）/ **A8 sourceText（原文保真，映射现状 content）**
   - A4 requester / A5 dept：system 类型（由服务端快照，不进 YAML 交互要素或标记 system）
   - **B 区（Why，识别业务需求时必填）**：B1 businessGoal / B2 businessBackground / B3 businessValue / B4 stakeholders（list）/ B5 businessRules（可空）/ **B6 upstreamGoal（所属战略目标，可空，追踪矩阵上游锚点，BR-T13 拆条溯源）** / B7 relatedDemands（list，可空）
   - **C 区（Who/What）**：C1 userRole / C2 userGoal / C3 useScenario（升级自 businessScenario，沿用 ok_when 规则）/ C4 useFrequency / C5 painPoint / C6 userCount（number）
   - **D 区（How）**：D1 functionDescription / D2 inputOutput / D3 businessRuleMap / D4 dataRequirements / D5 interfaceRequirements / D6 nfrRequirements（list）/ D7 exceptionHandling / D8 acceptanceCriteria（沿用现状规则）
   - 每个要素保留：`key / label / kind / required / ok_when / rule / ask_l1 / ask_l2 / ask_missing / vague_hint`（话术可参考现状 tech.yaml 与 H5 原型文案）
2. 新增标准级配置：
   - `type_signals`（PRD §4.3 判型信号表：业务/用户/功能三层关键词）——供 LLM 判型提示词
   - `granularity`（BR-T13）：`too_broad` 关键词（"提升…到…/全面/整体/战略"）与 `too_narrow` 关键词（"加个字段/显示/按钮"）及对应处理话术
   - `max_attempts`、`skip_phrases`、`follow_up_order` 按新要素重排
3. 迁移映射表（PRD §4.4）：旧六要素 → 新区位置，写入 YAML 注释或 `server/app/standards/migration_map.py`（title→A1、content→A8、businessScenario→C3、acceptanceCriteria→D8、techSubtype→A3 等），供历史草稿兼容读取

**验收**：
- `uv run pytest -k standards` 通过（loader/rules 对新 YAML 全量校验）
- 新增单测：30 要素数量、必填集合、enum 选项、B 区 conditional required 规则
- `python -c "from app.standards import loader; s=loader.get('TECH'); assert len(s.elements)==30"` 通过

---

### P2 Agent 后端升级：判型、拆解、粒度治理、修改留痕

**目标**：policy 与 guide 从"六要素追问"升级为"五区智能收集"，落实 PRD §5 全部功能点与 BR-T11/T12/T13、FR-08。

**执行**（`server/app/agent/policy.py`、`guide.py`、`schemas.py`、`llm_client.py` 提示词）：
1. **判型（FR-01）**：LLM 输出 `typeSignals`（业务/用户/功能 各置信度 + 依据原文片段）→ 前端卡片展示"我理解这是一个业务需求（因为提到部门目标/成本投入），对吗？" → 用户确认/改判后定稿；判型结果存 `elements.B` 触发条件与 `ext.typeRecognition`
2. **大段拆解（FR-02，D6 原文保真）**：用户一次性大段输入 → LLM 拆解到各区要素槽位（`structured` 输出）→ `demand.content`（A8）永久保留原话、`elements` 只放提炼值 → `field_sources[path]="agent"`。**提炼约束（FR-08）：不改原意、不增删事实**——写入 LLM 提示词 system 段
3. **多要素一句话拆解（用户确认口径）**：一句话同时含 A/B/C/D 区多个要素时，**拆解提炼进对应要素槽位**（每个槽位记独立来源），**原话完整保留在 A8 sourceText**；不把原话原样复制进多区。实现：`merge_structured` 已支持多 key 合并，补充 LLM 输出约束"每个事实仅落一个槽位，避免重复"
4. **粒度治理（BR-T13，新规则）**：
   - 识别"目标级"（过大，如"提升客户回访率到 80%"）→ 引导分解为可独立受理的子需求，**一次聚焦一条**，其余暂存草稿（split_from_id/split_group_id 预留，一期可仅标记 `ext.pendingSplits`，切分落库留到 V2 或本期按概念模型 §5 实现）
   - 识别"字段级"（过小，如"加个基金净值日期字段显示"）→ 向上补全上下文（所属功能/场景/用户角色）
   - 收敛标准统一为：**可验证 / 可追踪 / 可独立受理**
   - 话术与判定词配置进 tech.yaml `granularity`
5. **判质与追问（复用现状）**：`complete_elements` / `pick_follow_up` 对新 30 要素生效；追问历史仍写 `agent_message.structured_payload`（E8，零新增）
6. **修改留痕（FR-06）**：识别修改意图（"改一下/补充/其实不是…"）→ 定位要素 → 更新 elements + field_sources=user + revision+1 → **写 demand_change_log 一行（field_key/old/new/source/changed_by）** → 影响分析（改 B1 业务目标 → 提示可能影响 C/D 区，询问是否联动调整，PRD §5.6）→ 重评估下游要素
7. **草稿续报（FR-05）**：`status=DRAFT` 草稿可继续会话；标准快照判质结论 `quality_content_hash` 不变不重判（D5 已实现，回归确认）
8. **预算/IRB**：不实现任何预算逻辑；仅在标准/会话模型预留 `BUDGET_CHECK` 状态位注释（PRD §11）

**验收**（新增测试，`server/tests/`）：
- 判型：3 条典型业务/用户/功能文本各识别正确，且可被用户改判
- 拆解：一段 200 字混合文本拆出 ≥3 区要素，content 原话一字不变（断言相等）
- 提炼约束：LLM mock 输出含"新增事实"时被过滤（policy 层断言）
- 粒度治理：目标级/字段级样例各触发正确引导分支
- 修改留痕：修改 2 次 → revision=2、change_log 2 行、旧值正确
- 回归：`uv run pytest` 全绿

---

### P3 后端 API 与数据出口

**目标**：要素表单可读写、变更可查、详情可回放，支撑 BA 直接编写文档。

**执行**：
1. `app/api/demand.py`：
   - 草稿/正式需求响应体增加 `elements`（五区对象，A/B/C/D 分组）+ `quality` + `fieldSources` + `changeLogs`（联表 demand_change_log）
   - 提交时：校验 `elements` 与 `field_sources`、`revision` 乐观锁（更新需带 revision 条件）
2. `app/api/agent.py`：SSE 消息的 `structured` 改为五区结构；追加 `typeRecognition`（判型卡片）、`granularityHint`（粒度提示）字段（对齐 H5 原型交互）
3. `app/services/export.py`：需求导出（XLSX/详情）按 A/B/C/D/E 分区排版，A8 原文置首，E 区状态附注
4. `app/api/admin.py`：需求列表/质量统计支持按区过滤（可选，若 H5 原型有对应入口）

**验收**：
- 接口单测：提交五区草稿 → 详情返回 elements 完整、changeLogs 为空；修改 → changeLogs 增行
- `scripts/e2e_mvp.py --agent-mode none` 通过（独立手填闭环）

---

### P4 H5 前端升级（frontend/h5/，对齐 H5 原型 v1.0）

**目标**：按 `DemandHub_科技需求收集智能体_H5原型_v1.0.html` 实现交互（含"一段话示例"入口、五区表单、判型卡片、粒度提示、草稿与修改对话）。

**执行**：
1. **示例引导（原型新增入口）**：提报首屏提供"一段话示例"，用户可一键填入示例文本或直接粘贴大段需求；示例覆盖典型业务需求文本
2. **判型卡片（FR-01 前端）**：`AgentGuideSheet.vue` 增加判型结果卡："我理解这是一个__需求（依据：…原文片段），对吗？" → 确认/改判按钮 → 确认后按 B 区必填门槛继续
3. **五区表单**：`StandardField.vue` 升级为分区渲染（A 公共 / B 业务 / C 用户 / D 功能 / E 状态）；E 区只读展示（elementStatus/qualityComplete/canSubmit/来源/修改次数）；B 区含 **B6 上游业务目标** 输入（粒度治理拆条后可回溯）
4. **粒度提示（BR-T13）**：输入过短（字段级）→ 提示"补充所属功能/场景"；输入过大（目标级）→ 提示"先聚焦其中一条，其余保存草稿"
5. **拆解确认**：大段输入后展示"已拆解为以下要素"，逐槽位可改（elements 编辑）→ 保存
6. **修改对话（FR-06）**：会话中"改一下/补充…"→ 高亮受影响要素（B 改 → 提示 C/D 可能受影响）→ 确认联动
7. **草稿续报**：`views/mine/index.vue` 草稿列表 → 继续会话；详情页展示五区表单 + 质量 + 对话回放（PRD §4.1 页面要求）
8. **语音输入引导（演进路线 V1.x 零开发项）**：仅补引导文案——输入框 placeholder 与首次提示语（如"可长按语音转文字，直接说需求"），复用手机输入法语音能力，不写任何语音识别代码
9. 预算相关 UI 一律不出现（原型已撤除）

**验收**：
- `npm run typecheck` 通过；`npm run test`（vitest）通过；`npm run build` 通过
- 组件级 vitest：判型卡片确认/改判流程、拆解结果展示、粒度提示触发
- 手工场景（对 3307 后端联调）：粘贴大段需求 → 判型 → 追问 → 草稿 → 修改 → 提交，全链路可走通

---

### P5 全链路验收

**验收场景清单（对 3307 本机后端 + 前端 dev 执行）**：
1. 新用户打开提报页 → 看到"一段话示例" → 一键填入示例 → 提交
2. 大段粘贴（含业务+用户+功能混合）→ 判型卡片正确 → 确认 → 五区要素已拆解、A8 原文完整 → 必填空缺被追问
3. 字段级需求（"加个基金净值日期字段显示"）→ 收到补全提示 → 补全后继续
4. 战略级需求（"提升客户回访率到 80%"）→ 收到分解引导 → 聚焦一条 → 其余存草稿
5. 对话中修改（"B1 改一下：目标是…"）→ 定位要素 → 影响提示 → 联动确认 → changeLog 可查
6. 草稿中断 → 我的需求列表续报 → 提交 → 详情页五区表单 + 质量 + 回放完整
7. `uv run pytest` 全绿、`uv run ruff check app tests alembic` 通过、`npm run build` 通过、`scripts/e2e_mvp.py --agent-mode mock` 通过（LLM 走 Ark mock）

---

## 3. 风险与约束

| 风险/约束 | 处置 |
|---|---|
| 六要素→五区升级影响既有草稿 | P1 迁移映射表兼容读取；存量草稿 elements 为空时回退读 ext |
| 判型模型效果 | 判型结果必须用户确认/改判（人工兜底）；信号表可配置 |
| LLM 提炼"增删事实" | FR-08 提示词 + policy 层过滤 + field_sources 留痕可审计 |
| 预算/IRB 后续需求 | 接缝已留（PRD §11、B5–B8 位），恢复零 DDL |
| 实例切分（BR-T11）落库 | 一期可仅打标 `ext.pendingSplits`；如需落库按概念模型 §5 split_from_id/split_group_id 实现（DDL 已备） |
| Windows 本机 | `NO_PROXY=127.0.0.1,localhost`；tzdata 勿删；MySQL 直连 3307 |

## 4. 交付物清单

- 后端：`models.py`、`0002_elements_change_log.py`、`standards/tech.yaml`（五区）、`agent/policy.py`、`agent/guide.py`、`agent/schemas.py`、`agent/llm_client.py`（提示词）、`api/demand.py`、`api/agent.py`、`services/export.py`
- 前端：`AgentGuideSheet.vue`、`StandardField.vue`、`QualityList.vue`、`views/demand/detail.vue`、`views/mine/index.vue`、`api/agent.ts`、`api/demand.ts`
- 测试：`server/tests/test_*`（判型/拆解/粒度/修改留痕）、`frontend/h5/src/**/*.test.ts`

## 5. 执行顺序建议

P0 → P1 → P2 → P3 → P4 → P5。P0/P1 无外部依赖可先行；P2 依赖 P1；P4 依赖 P3 接口；每阶段完成即跑对应验收，不跨阶段堆积。
