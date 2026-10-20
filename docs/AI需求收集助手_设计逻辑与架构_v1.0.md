# AI 需求收集助手 · 设计逻辑与架构

> 适用场景：DemandHub 提报引导（SUBMIT_GUIDE）。帮助提报人把随口一句话、整段粘贴文本、语音转文字，通过多轮对话收敛为一张符合五区质量标准的结构化需求单。
> 代码位置：`server/app/agent/` + `server/app/standards/`。

---

## 1. 核心设计哲学：模型只做抽取判质，决策全归纯函数

整个助手的第一性原理写在 [policy.py](../server/app/agent/policy.py) 头注释里：

> **模型只能抽取判质；来源、目标、话术与完成标记由纯函数决定。**

职责切分：

| 角色 | 职责 | 不做的事 |
| --- | --- | --- |
| **LLM（大模型）** | ① 从消息中抽取字段增量（structured）<br>② 对每个要素打质量票（OK/VAGUE/MISSING）<br>③ 判型投票（business/user/function 三层置信度）<br>④ 轻重判定票（light/standard）<br>⑤ 意图识别（answer/supplement/chitchat/question/command）<br>⑥ 生成四段式需求概述（ext.overview） | 不提问、不选择下一个要素、不生成任何面向用户的固定话术、不声称已保存/提交、不改写用户已填字段 |
| **policy.py（纯函数）** | ① 合并模型输出与旧表单（来源保护）<br>② 要素状态仲裁（规则层优先于模型票）<br>③ 追问目标选择（pick_follow_up）<br>④ 全部话术组装（reply_for）<br>⑤ 提交门槛判定（can_submit）<br>⑥ attempts 计数与 SKIP 继承 | 不调模型、不碰数据库 |
| **rules.py（规则层）** | 硬性格式校验（field_error）与软质量判定（assess） | 与渠道无关，所有保存入口共用同一标准 |

这样设计的原因（代码中多处"拍板"注释佐证）：**模型自述不可靠**——AI 说"都记好了"时可能其实丢了信息；完成标记、打回原因引述、方案播报等关键承诺全部由模板层保证，可测试、可审查、行为确定。

---

## 2. 在整体智能体架构中的位置

```
用户（H5/PC 提报页）
   │  POST /agent/guide/chat(/stream)   ← SSE 流式
   ▼
api/agent.py  ──────────────────────────  路由层：会话创建、消息列表、对话入口
   ▼
agent/guide.py  GuideService             编排层：prepare → prompt → LLM → policy → 落库
   │    ├───────────────┐
   ▼                   ▼
agent/llm_client.py   agent/policy.py      传输层（方舟 Ark）/ 决策核心（纯函数）
   │                   │
   ▼                   ▼
agent/schemas.py      standards/           契约层 / 标准层（schema+rules+loader+yaml）
   │                   │
   ▼                   ▼
db (AgentSession/AgentMessage/Demand/PromptVersion)
```

平行的另一条智能体链路：

- **SUBMIT_GUIDE（提报引导）**：本文主角，走 `guide.py + policy.py`，服务对象是提报人。
- **HANDLE_ASSIST（处理辅助）**：`services/assist_service.py`，服务产品经理（生成澄清问题、解决方案草稿），只复用 `llm_client.py`，**不复用 policy.py**。
- `agent/overview.py`：手改要素后的"需求概述"后台重写（即发即忘的异步任务，锁内串行、失败静默跳过）。

---

## 3. 文件职责一览

| 文件 | 职责 |
| --- | --- |
| [api/agent.py](../server/app/api/agent.py) | 路由：`/agent/session` 建会话、`/agent/guide/chat` 同步对话、`/agent/guide/chat/stream` SSE 流式对话 |
| [agent/guide.py](../server/app/agent/guide.py) | **编排层 GuideService**：读快照→无锁模型请求→短事务复验保存→发送；requestId 幂等重放；格式错误修复重试一次 |
| [agent/policy.py](../server/app/agent/policy.py) | **决策核心**：合并、仲裁、追问选择、话术生成、兜底事件接续（resume_follow_up）；全部为纯函数 |
| [agent/schemas.py](../server/app/agent/schemas.py) | 请求（GuideChatRequest）、响应（GuideResult）、模型输出（ModelOutput）契约；`parse_model_output` 宽容解析模型 JSON |
| [agent/llm_client.py](../server/app/agent/llm_client.py) | 方舟 Ark 客户端：流式 JSON、瞬时错误自动重试 1 次、连续失败熔断冷却、内容审核拦截识别（1405）、thinking 参数自动降级 |
| [agent/overview.py](../server/app/agent/overview.py) | 手改保存后台触发概述四段式重写（problem/userScene/goal/acceptance） |
| [agent/prompts/submit_guide.md](../server/app/agent/prompts/submit_guide.md) | 系统提示词模板：`{{today}}` 注入当天日期（防错补年份）、`{{standard_section}}` 注入三套标准 JSON |
| [standards/schema.py](../server/app/standards/schema.py) | 标准的数据模型：Standard / Element / Rule / Granularity / TypeSignals，含合法性校验 |
| [standards/rules.py](../server/app/standards/rules.py) | 硬性校验（field_error）、软质量判定（assess）、白名单过滤（filter_form）、提交门槛（schema_errors）、判型生效口径（business_confirmed） |
| [standards/loader.py](../server/app/standards/loader.py) | 加载 yaml 标准、按内容 hash 落 PromptVersion 不可变快照（每次对话留痕提示词+标准版本） |
| [standards/tech.yaml](../server/app/standards/tech.yaml) | 科技需求五区标准（26 要素的话术、规则、锚定配置）；另有 matl.yaml / train.yaml |

---

## 4. 五区要素标准（话术与规则的载体）

科技需求标准（TECH）共 26 个交互要素，按区组织：

| 区 | 定位 | 要素 |
| --- | --- | --- |
| **A 公共** | 所有需求必填的结构信息 | A1 标题（auto_fill 系统提取）、A2 类型、A3 子类（AI 自动归类不评估）、A4 提报人（system）、A5 部门（system）、A6 紧急度、A7 期望交付时间、A8 原话底稿（系统回填） |
| **B 业务（Why）** | 仅判型为"业务需求"时激活必填 | B1 业务目标、B2 业务背景、B3 业务价值、B4 干系人、B5 业务规则、B6 上级目标、B7 关联需求 |
| **C 用户（Who/What）** | 用户故事 | C1 目标用户角色、C2 用户目标、C3 使用场景、C4 使用频率、C5 用户痛点、C6 用户规模 |
| **D 功能（How）** | 系统行为 | D1 功能描述、D2 输入/输出、D3 规则映射、D4 数据需求、D5 接口需求、D6 性能安全、D7 异常边界、D8 验收标准、D9 建议方案（提报人设想，不评估） |

每个要素在 yaml 中携带完整对话配置：

- `ok_when` / `rule`（min_len、max_len、any_of、any_of_regex）/ `vague_hint`：质量判定规则；
- `ask_missing` / `ask_l1` / `ask_l2`：三级追问话术模板；
- `anchor_key` / `anchor_key2` + `ask_anchor` / `ask_anchor2`：锚定追问配置（见 §7.2）；
- `required` / `system` / `auto_fill` / `assessed`：流程属性。

---

## 5. 对话流程：一轮消息的完整生命周期

```
① prepare（guide.py）
   会话归属校验 → 草稿状态(DRAFT/NEED_INFO)与 revision 乐观锁 → requestId 幂等重放
   → 拉最近 20 条历史 → 取上一轮对话结果快照（排除 manualChange/attachmentReceipt/
   returnNotice/modeChange/typeChange 等播报消息）→ A8 底稿首轮回填（来源=user）
   → 打回引述判定（历史消息里是否已引述过）

② build_prompt
   系统提示词 = 模板 + {{today}} + 三套标准 JSON
   用户消息 = {message, form, fieldSources, previousElements, askedTarget}

③ 调模型（llm_client.stream_json）
   流式读完整 JSON → parse_model_output 解析
   格式错误 → 追加一条修复指令重试一次 → 再失败按 1401（AI 不可用）
   内容审核拦截 → 1405（提示改写文案，不计熔断）

④ policy.process（纯函数，详见 §6~§9）
   意图分流 → 合并抽取 → 判型/轻重合并 → 状态仲裁 → 计数继承
   → 算提交门槛 → 选追问目标 → 组装话术

⑤ 短事务落库（guide.py execute）
   with_for_update 复验 revision/状态（防模型等待期间草稿被改/提交）
   → apply_agent_patch 写表单与 field_sources
   → ensure_snapshot 留 PromptVersion 快照
   → append USER + ASSISTANT 消息（payload 含 intent，供提交时配对过滤闲聊轮）
   → 更新 session.asked_target

⑥ SSE 输出：processing → message(reply) → structured(结构化结果) → done
   只有提交成功才发回复，失败/取消不补写。
```

**对话外事件接续**（不调模型）：手改要素、附件回执、打回重进等场景走 `policy.resume_follow_up`——规则层重算状态、从上一轮快照继承 attempts/SKIP（不按对话答错计数）、选下一追问目标并生成话术，payload 结构对齐对话结果供前端回放。

---

## 6. 意图分流：五种意图五条路

模型每轮先判定"用户在做什么"（`intent.kind`），policy 按意图走不同分支：

| 意图 | 含义 | policy 行为 |
| --- | --- | --- |
| `answer`（默认） | 在回答当前问题 | 正常合并抽取；当前问题答得不好 → attempts +1 |
| `supplement` | 补充/纠正之前的内容（没答当前问题） | 照常合并抽取，但**不按答错惩罚**（attempts 不计）；回复 = 引述式确认（"「XX」已按你补充的更新：…"）+ 桥接"回到刚才的问题——" + 追问 |
| `chitchat` | 纯寒暄/与需求无关 | **不抽取、不判型、不判轻重、不计数**；误回填的底稿连来源一起清除；首轮只发简短引导不追问（单问题原则），中期短承接 + 重问当前问题 |
| `question` | 向 AI 提问（如"验收标准是什么意思"） | 照常合并但不计数；回复 = 要素级白话解释 + 桥接回当前问题；若解释的正是当前问题要素，解释本身即追问不重复 |
| `command` | 流程指令（如"提交吧"） | 照常合并但不计数；回复只聚焦指令本身——可提交就说怎么提交，不可提交列缺失必填项；不叠加模式播报/方案播报/打回引述（文不对题） |

意图落库在 ASSISTANT 消息 payload 里，提交时按 request_id 配对，**排除闲聊/提问/指令轮的用户消息**，保证 A8 底稿只拼接有效对话。

---

## 7. 话术规则体系

### 7.1 总原则

- **单问题原则**：一条回复最多一个问句（2026-10-20 拍板）。
- **大白话**：不出现"业务需求/用户需求/功能需求"分层术语、不出现"原始提报文本"等用户听不懂的要素名。
- **引述式**：重问/确认时引用用户原话片段（`{snippet}`，截断 20~30 字 + "…"），避免"我不是填了吗"的观感。
- **模板三层**：所有追问话术来自 yaml 配置而非模型即兴——`ask_missing`（首问）→ `ask_l1`（引述 + 说差距再追问）→ `ask_l2`（直接给参考句式，如"把__（指标）从__提升到__"）。

### 7.2 锚定追问（首次追问不重复问已知信息）

- **单锚定**：B1 业务目标 ← C2 用户目标（上下游因果）、B4 干系人 ← C1 目标用户（受益方推导）。引述已填关联要素组织问句："用户侧要完成「晨会前查持仓」——那部门层面想达成什么业务目标？"
- **双锚定**（C3 使用场景 ← C1 角色 + C2 任务）：两个锚值都已填时用 `ask_anchor2`——"使用场景我先记着：「客户经理」要「晨会前查持仓」——有不对的地方直接纠正。再补一句：大概在什么时间、多久用一次？"
- 锚值为空时逐级回落到普通追问模板。

### 7.3 分场景话术

| 场景 | 话术 |
| --- | --- |
| 首轮闲聊 | `CHITCHAT_GREET_FIRST`："你好！我在，直接说你的需求就行……"（前端已有完整开场白，不重复发） |
| 中期闲聊 | `CHITCHAT_GUIDE`："我在，咱们继续把需求记清楚。" + 重问当前问题 |
| 无底稿开场 | `DESC_INVITE`："请先用一句话描述一下你的需求，比如「报表想加个按机构导出」。"（一句话同时喂饱底稿回填、要素抽取、轻重判定） |
| light 模式问 D8 | 白话问期望效果 + 顺带确认 AI 代拟标题："标题我先记为「XX」，不合适直接告诉我改什么。这个需求期望的效果是什么？" |
| 手改后仍不达标重问 | `_quoted_reask`："你填的「验收标准」『…』我记下了，不过还不够具体——" + 追问模板（手填值是用户权威，只提示不擅改） |
| 补充确认 | `_supplement_confirm`：列出本轮值变化的要素并引述新值片段请用户当场纠正（系统字段/底稿/标题/类型不确认） |
| 模式播报 | 首判 light："这个需求听起来是个小改动，我按轻量提报帮你登记，只确认几项关键信息就行。"；light→standard 升级："这个需求听起来改动面不小，我按常规需求帮你把基本信息问齐。" |
| D9 方案播报 | 引述原文片段后置告知："你说的「…」我先记到「建议方案」里了……最终做法由产品和技术评估后再定。" |
| 打回引述 | `RETURN_QUOTE_PREFIX`："这条需求之前被打回过，打回原因是「…」。"——补充会话**只引述一次**（`return_quote_seen` 按历史消息判定） |

### 7.4 完成话术矩阵

按 触发方式（dialog 对话 / attachment 附件 / manual 手改 / enter 进页面 / event 事件）× 单据状态（草稿 / 打回）× 是否填齐 分别配置，例如：

- 草稿 + 对话 + 填齐（standard）："都记好了，请核对一下表单。该填的都齐了，可以提交。没填或不太完整的可选项会在表单里标出来，不影响提交，以后能补；产品经理调研后也可以补。"
- 打回 + 附件 + 填齐："可以点「确认提交」重新提交。"
- 追问次数用尽但必填仍缺（兜底）："我这边问得差不多了。请在下方表单里把标红星※的必填项补齐后提交。"

### 7.5 快捷回复（quick_replies）

枚举要素给出选项标签（普通/紧急/特急）；**非必填项答满一次后追加"后续补充"**，与 `skip_phrases`（不知道/跳过/后续补充/再说吧……）整句匹配联动，识别后标 SKIP 不再追问。

---

## 8. 追问逻辑：`pick_follow_up`

选下一个追问目标的完整决策顺序（[policy.py L232-306](../server/app/agent/policy.py)）：

```
① 急单门控插队（最优先）
   urgency ∈ {紧急, 特急} 且 expectDeliveryAt 未填
   → 插队追问期望交付时间（"紧急或特急请说明期望时间"的话术承诺不落空）
   → 日期填上或问满即自动恢复正常顺序；仅 TECH 生效

② light 模式：固定最小集顺序
   acceptanceCriteria（期望效果）→ urgency（紧急度）
   只问真空着（MISSING）的项，每项最多 1 次，合计 ≤ 2 轮
   标题(A1)/底稿(A8) 是系统提取项（auto_fill），永不追问

③ standard 模式：资格过滤后的稳定排序
   排序：A/C/D 必填（yaml 原顺序，urgency 沉底最后）→ B 区（仅业务需求）→ follow_up_order
   资格（eligible）排除：
   - auto_fill 系统提取项
   - 已 OK / 已 SKIP / attempts 满 2 次
   - 非业务需求时的 B 区要素
   - 【可提交即停问软质量】必填门槛已达成后，有值但不够好的（VAGUE）非空必填项不再主动问；
     MISSING（真空着）不受此限
```

关键拍板口径：

- **A/C/D 先问完、B 区沉底**：先补"给谁用、什么场景、痛点、验收"等具体信息，再问业务要素；与提交门槛 active_zones 同口径。
- **紧急度沉底**（2026-10-15）：排期类信息待需求本体问齐后再确认，急单门控承接恰好收尾。
- **问满两次放过**（max_attempts=2）：手改路径同口径——本轮手改过仍不达标记 1 次，没碰的不记，消灭"手改反复重问无终点"。

---

## 9. 质量判定与计数机制

### 9.1 状态仲裁（complete_elements）

- **规则层为主**：`assess()`（rules.py）对每个要素判定 OK / VAGUE / MISSING——空值即 MISSING；硬性格式错（日期非法、超字数、枚举越界、过去日期）判 VAGUE；软质量规则（短句含歧义词、min_len、缺关键词/正则）判 VAGUE。
- **模型票仅在狭窄窗口生效**：规则判 VAGUE 且无硬性格式错误时，模型票可 OK 抬升或补质量 note；模型对已有有效值报 MISSING/VAGUE 视为自相矛盾被忽略（防"已填字段被反复追问"）。
- A8 底稿（content）非空即 OK，不做任何软质量降级。

### 9.2 attempts 计数（inherit_and_count）

- 仅 `answer` 意图且答的是当前问题、仍不达标 → attempts +1（上限 2）；答 OK 清零。
- supplement/question/command 不计数（用户没作答当前问题，不按答错惩罚）。
- 用户整句说跳过语 → 非必填项标 SKIP（"用户选择后续补充"），SKIP 状态跨轮继承，值变了才复活。
- 状态 OK 后 attempts 清零，可重新追问。

### 9.3 合并保护与防编造（merge_structured）

- **来源保护**：`field_sources=user` 的字段（含用户主动清空）模型禁止改写。
- **状态词过滤**：模型把 "VAGUE"/"MISSING" 当值写进字段按未输出处理。
- **FR-08 数字溯源**：text 要素中的数字必须可溯源到本轮消息或旧值，含新增数字视为编造事实、整值丢弃。
- **畸形分级**：结构性错误（ext 非对象、elements 非嵌套、非 list 要素输出数组）整轮拒绝走修复；单个非法值（日期写"本周"）只丢该值不报错；demandTypeCode 非法单独严控。
- **白名单**：`filter_form` 只保留标准内字段；`returnReason` 由系统管理、不读模型输出（防伪造打回原因）。

### 9.4 判型与轻重（三层票 + 粘性）

- **判型**（typeSignals）：business/user/function 三层独立置信度 + 依据原文；合并取历史最高；`business ≥ 0.5 且占优`才激活 B 区必填与追问；用户 confirmed 定稿不被模型覆盖。
- **轻重**（modeSignal）：light（换 logo/改文案等小改动，4 项最小集快速通道）/ standard。
  - standard 粘性：判过 standard 不得降回 light（防对话后期悄悄放宽口径）；
  - 用户手动定过口径（origin=user）AI 双向不得翻转；
  - 缺省 standard；light→standard 升级当轮播报，首判 light 也播报（口径显性化）。

### 9.5 提交门槛（can_submit）

- standard：`schema_errors` 按必填 + active_zones（业务需求 = A/B/C/D 四区，否则 A/C/D）；
- light：按 `LIGHT_REQUIRED_KEYS` = {title, demandTypeCode, urgency, acceptanceCriteria} 最小集放行；
- auto_fill 项（标题）豁免必填门槛（提交前由 submit 兜底链保证非空）；格式错误照常拦。

---

## 10. 辅助治理机制速查

| 机制 | 说明 |
| --- | --- |
| **粒度治理**（BR-T13/FR-10） | too_broad（"提升/全面/平台化"等）且 D 区未填 → 提示拆细；too_narrow（"加个字段/按钮"等）且 C 区未填 → 提示补场景；收敛标准统一为"可验证、可追踪、可独立受理" |
| **影响分析**（FR-06） | 已填的 B 区要素被修改时，提示"C/D 区内容可能也要跟着改" |
| **实例切分**（BR-T11） | 一段话识别多条可独立受理需求 → 只抽最聚焦一条，其余打标 `ext.pendingSplits` 待用户确认 |
| **概述生成** | 每轮整体重写四段式摘要（problem/userScene/goal/acceptance），每段"详细描述｜一句话概括"；手改后由 overview.py 后台异步重写，失败保留旧概述 |
| **打回补充** | returnReason 存 ext（系统管理）；打回当刻发完整通知（returnNotice）；会话重开后只引述一次原因；打回单要素本就齐全，完成话术用简短行动指引而非新手长话术 |

---

## 11. 可靠性与一致性设计

| 设计 | 实现 |
| --- | --- |
| **幂等** | requestId + requestHash：同 requestId 重发直接回放已存结果，不同输入报 409 |
| **并发** | 会话级 asyncio.Lock；模型等待期间不占数据库连接（读快照后显式 rollback，写时短事务 + with_for_update 复验 revision/状态） |
| **熔断** | LLM 连续失败达阈值冷却 60s；瞬时错误（429/5xx/超时）自动重试 1 次；内容审核拦截单独 1405 不计熔断 |
| **留痕** | 每轮对话落 PromptVersion 快照（标准原文 + 提示词模板 + 渲染后提示词，内容 hash 去重）；消息带 prompt_tokens/latency_ms 等元数据 |
| **快照回放** | 上一轮表单快照只认真正的对话结果消息，播报类消息（手改/附件/打回/口径改判）不参与，防误用丢要素状态 |

---

## 12. 一句话总结

> **提示词（submit_guide.md）+ 标准（yaml）喂给模型做"抽取与判质"，policy.py 用纯函数做"合并、仲裁、选问、说话"，guide.py 用事务与锁保证"每轮对话恰好落库一次"** —— AI 负责理解人话，规则负责守住流程与承诺。
