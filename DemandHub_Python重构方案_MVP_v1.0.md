# DemandHub · Python 重构方案（MVP v1）

| 项目 | 内容 |
|---|---|
| 文档名称 | DemandHub Python 重构方案（MVP 第一版） |
| 版本 | v1.3（评审修订后的实施基线） |
| 编制日期 | 2026-09-30 |
| 配套文档 | `DemandHub_Python改造实施计划_v1.0.md`（任务级实施计划，供执行方使用） |
| 基线代码 | `main@783c80f`（含火山方舟 RealLlmClient、P11 JSON 契约提示词） |
| 部署约束 | 公司 H5 发布平台：`backend-image-push` + `h5-package-build` 两个 skill |
| 读者 | 项目负责人、开发、原 Java 版作者 |

---

## 0. 一页结论

**目标**：用一个 Python 单服务 + 一个裁剪后的 H5，实现"以 Agent 对话方式录入需求 → 按需求标准追问 → 结构化落库 → 记录/整理导出"的最简闭环，并能直接走公司容器化发布流程上线。V1 只做**收集、完善、整理记录**；分派与交付不做。无存量数据、未上线，不存在迁移问题。

**设计原则（第一性原理）**

V1 的唯一产出物是"一条符合标准的、可归属、可检索的结构化需求记录"。生产它需要四个动作：启发追问、抽取字段、判定质量、写入记录。字段抽取和语义判质由模型辅助；追问目标、话术、保存及提交由代码执行。由此导出五条原则：

1. **模型判断、代码决策**。模型负责抽取字段与要素判质，代码先合并本轮结果，再选择下一追问目标。V1 使用标准 YAML 中的话术生成追问，不增加第二次模型调用；保存实际问出的 `askedTarget`，后续计次和跳过均以它为准。模型抽取仍可能出错，用户确认、字段来源保护及提交校验共同约束正式记录。
2. **schema 闭集**。字段集合固定；需求类型、科技子类和紧急度按枚举校验，物料/培训子类按标准保留为有长度限制的文本。所有入口共用类型、长度、日期和选项校验，非法值由服务端拒绝。
3. **表单锚定，对话加速**。屏幕上始终有表单和要素完备度清单；对话的产出是回填表单、标绿标黄；记录的是用户确认时的表单，不是聊天内容。不做"纯聊天受理机器人"。
4. **一次成型优先，追问是例外**。入口是"随口说一段 / 粘一段 / 语音转文字"，模型一次性给出草稿 + 缺口清单；多数情况用户直接补表单即可提交，追问只在关键要素模糊时出现，同一要素最多两轮。
5. **API-first，标准即资源**。服务端是 headless 开放能力，需求标准通过 `GET /standards/{type}` 暴露为单一事实来源；H5（嵌创金零售）是第一个客户端，CLI / Skill / 企微机器人后续都是同一组 API 上的薄客户端。无论哪个渠道进来，`POST /demand/{id}/submit` 都在服务端按同一标准复判一次，保证记录质量口径一致。

**核心取舍**

| 维度 | 现状（Java 一期） | MVP（Python） |
|---|---|---|
| 后端形态 | 7 Maven 模块，网关 + 4 微服务 + 单体装配双形态，18.5k 行 | 1 个 FastAPI 服务，预计 2.5k～3.5k 行 |
| 中间件 | MySQL、Redis、MinIO、Nacos、RocketMQ ×2 | 仅平台共享 MySQL（无 Redis / MQ / 对象存储） |
| 数据表 | 46 张 | 6 张 |
| 前端 | PC（9.6k 行）+ H5（4.9k 行） | 仅 H5，裁剪至约 2.5k 行，复用现有 Agent 对话组件 |
| 需求状态 | 12 态状态机 + 挂起叠加态 | 3 态：`DRAFT / SUBMITTED / CLOSED` |
| Agent | 方舟 JSON mode，非流式 + 切片假流式，推理模型 90s 超时 | 方舟流式抽取；代码在结果校验后生成下一追问；模型 endpoint 可配置，按实测验收 |
| 部署 | 12～13 容器 compose，平台上需自建 Redis/RocketMQ 镜像绕规则 | 1 个业务镜像 + 1 个 H5 zip，完全符合平台规则 |

**不做的（明确移出 v1）**：受理/分派/领取、SLA、看板报表、站内信与企微推送、组织树与角色授权、用户合并、附件、PC 管理端、处理辅助 Agent（调研问题/方案初稿）、RAG、CLI / Skill 客户端（API 稳定后 1～2 天可补，见 §10 P7）。

**预计工期**：1 人约 10～12 个工作日（含上线联调）。

---

## 1. 从现有仓库继承什么

重构不等于从零开始。以下资产按"直接移植 / 转成配置 / 仅做参考"三档继承，避免重复踩坑。

### 1.1 直接移植（逻辑等价翻译成 Python）

| 来源（Java） | 去向（Python） | 说明 |
|---|---|---|
| `agent/llm/RealLlmClient.java` | `app/agent/llm_client.py` | 方舟 OpenAI 兼容调用、JSON 解析容错、连续失败计数 + 冷却降级、`normalizeStatus` 归一 |
| `system/sso/ChuangjinLsSsoClient.java` + `SsoSignUtil.java` + 两个单测 | `app/sso/chuangjin_ls.py` + `tests/test_sso.py` | verify 回源 HMAC-SHA256 签名、`X-App-Key/Timestamp/Nonce/Sign` 头、40001～40005 错误码映射、AC-07 文案、熔断（3 次 / 30s） |
| `common/config/DatabaseUrlEnvironmentPostProcessor.java` | `app/config.py` | 解析平台下发的 `DEMANDHUB_DATABASE_URL`（`mysql://user:pass@host:port/db`） |
| `deploy/h5pub/contract-mock/contract_mock_verify.py` | `tests/contract_mock.py` | 已是 Python，创金零售 verify 契约 Mock，本地/测试环境直接复用 |
| `demand/service/DemandNoGenerator.java` 规则 | `app/services/demand_no.py` | `TECH-YYYYMMDD-NNN` 编号规则，用 `demand_no_seq` 行锁实现 |
| `frontend/h5` 的提报、对话、我的需求和详情页面 | 复用视觉组件并升级交互/API | 前后端共同升级；认证、草稿关联、字段来源、SSE 终态均需修改，不承诺旧契约零改动 |

### 1.2 转成配置（业务知识沉淀为数据文件）

| 来源 | 去向 | 说明 |
|---|---|---|
| `deploy/mysql/init/09-ark-llm-prompt.sql` 中 `SUBMIT_GUIDE` 提示词 | `app/agent/prompts/submit_guide.md` | 已是完整 JSON 契约，抽取与判质定义由标准文件注入；模型不得自行追问或宣告已保存，追问在代码合并本轮结果后生成 |
| `MockLlmClient.java` 中的 rubric 规则（六要素、四态、歧义词表、追问阶梯、attempts/SKIP 粘性） | `app/standards/tech.yaml`（+ `matl.yaml`、`train.yaml`） | **这是"我们对需求的标准"的正式载体**，业务可直接改文件，不改代码 |
| `MockLlmClient` 的关键词 → 字段映射、`phase7_selftest.py` 的对话样例 | `tests/eval/cases/*.yaml` | 作为 Prompt 回归评测集（约 20 条），每次改提示词跑一遍 |
| `report/index.vue` 中按科技子类展开的补充字段（devFeatures / dataDimensions / intTargetSystem / opsProblem …） | `tech.yaml` 的 `subtype_fields` 段 | 作为"非阻塞补充要素"，Agent 顺带抽取但不追问 |

### 1.3 仅做参考

BRD / SRS / 架构 / 数据库设计文档保留为后续阶段路线图。Java 后端、PC 前端、旧 compose 编排在 MVP 上线后**从仓库删除**（git 历史仍可追溯，无需 `legacy/` 目录）；开发期间不改动 `backend/`，避免与新代码互相干扰。

---

## 2. 目标架构

```
 客户端层（薄）
 ┌──────────────────────────────┐  ┌──────────────────────────┐
 │ H5（V1 唯一客户端）            │  │ CLI / Skill / 企微机器人   │
 │ 创金零售 ──ticket 302──▶ 静态 zip│  │（后续；先 GET /standards   │
 │ 发布平台 /h5/<route-key>/     │  │ 再收集，最后 POST /demand）│
 └──────────────┬───────────────┘  └─────────────┬────────────┘
                │  fetch /demandhub-api/**（Kong 路由）│
                ▼                                 ▼
          demandhub-api（FastAPI，headless，单容器，1 副本起）
          ├─ /standards  需求标准（只读资源，单一事实来源）
          ├─ /auth       渠道 SSO 换 JWT / 开发期简易登录
          ├─ /agent      会话、SSE 流式对话（模型判断）
          ├─ /demand     草稿、提交（服务端复判 + 编号 + 归属，代码决策）、我的需求、导出
          ├─ /admin      全量列表与导出（白名单用户）
          └─ /health
                │                      │
     平台共享 MySQL 8            火山方舟（OpenAI 兼容）
     （6 张表，JSON 列）          chat：配置的方舟 endpoint；无 embedding
                                       │
                              创金零售 verify（HMAC 回源）
```

**Agent 上下文以明确的需求草稿为边界**：身份由认证注入，标准来自固定版本，表单及字段来源由草稿保存，会话必须绑定该草稿。每轮加载最近 20 条消息和完整最新草稿、上一轮 `askedTarget`。固定输入不保证模型输出确定；未知事实保持待确认，不靠模型猜测记录归属或目标。V1 不做相似需求检索。

**无 Redis**：JWT 无状态（access 8h，单 token，不做 refresh），登录失败锁定、限流用进程内计数即可（MVP 单副本）。
**无 MQ**：所有操作同步完成；无需要异步解耦的下游。
**无对象存储**：v1 不做附件。

---

## 3. 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 运行时 | Python 3.12，`python:3.12-slim` 镜像 | 平台典型后端形态；镜像约 150MB |
| Web | FastAPI + uvicorn | 原生 async、SSE（`StreamingResponse`）、Pydantic 校验、自动 OpenAPI |
| ORM / 迁移 | SQLAlchemy 2.0（async，`asyncmy` 驱动）+ Alembic | 平台只给一个 `DATABASE_URL`，迁移随容器启动执行 |
| LLM | `openai` SDK（`base_url` 指向方舟）| 官方 OpenAI 兼容，支持 `stream=True` + `response_format=json_object`；比手写 httpx 少一半代码 |
| 上游流式 | OpenAI 兼容 SSE | 累积抽取结果；最终追问等待校验与保存，不依赖半截 JSON |
| HTTP 客户端 | httpx（async） | SSO verify 回源 |
| 鉴权 | PyJWT（HS256） | 与现有 JWT 语义一致 |
| 配置 | pydantic-settings | 全部 env 注入，`.env.example` 入库、`.env` 不入库 |
| 导出 | openpyxl（xlsx）+ 内置 Markdown 渲染 | "整理"需求的最简形式 |
| 测试 | pytest + pytest-asyncio + respx（mock 方舟/verify） | 复用 Java 单测用例 |
| 代码质量 | ruff + mypy（strict 关闭） | 轻量 |

**明确不引入**：LangChain / LlamaIndex 等编排框架（一个提示词 + 一个 JSON 契约，框架只会增加不透明度）、Celery、Redis 客户端、向量库。

---

## 4. 数据模型（6 张表）

```sql
-- 用户（渠道回源建号，无密码、无组织树）
dh_user(
  id BIGINT PK AUTO_INCREMENT,
  name VARCHAR(64) NOT NULL,
  wecom_userid VARCHAR(64) UNIQUE,          -- 创金零售 verify 回传，匹配键
  phone VARCHAR(32), employee_no VARCHAR(32), email VARCHAR(128),
  dept_id VARCHAR(32), dept_name VARCHAR(128), dept_path VARCHAR(512),
  channel VARCHAR(32) NOT NULL DEFAULT 'CHUANGJIN_LS',
  status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE/DISABLED
  last_login_at DATETIME(3), created_at, updated_at
)

-- 需求（基表 + JSON 扩展，替代 3 张类型扩展表）
demand(
  id BIGINT PK AUTO_INCREMENT,
  demand_no VARCHAR(40) UNIQUE NULL,         -- 草稿为空，提交事务内生成 TECH-20260930-001
  title VARCHAR(256) NULL,
  demand_type_code VARCHAR(32) NULL,         -- 草稿可未知；提交必填 TECH/MATL/TRAIN
  subtype_code VARCHAR(32),                  -- SYS_DEV/DATA_RPT/SYS_INT/OPS_OPT/OTHER
  content TEXT NULL,                         -- 草稿允许不完整，提交必填
  urgency VARCHAR(16) NOT NULL DEFAULT 'NORMAL',
  expect_delivery_at DATE,
  ext JSON,                                  -- businessScenario/acceptanceCriteria/valueImpact/relatedSystem/子类补充字段
  quality JSON,                              -- 提交时刻的要素 rubric 快照 [{key,status,note}]，用于整理与统计
  field_sources JSON,                        -- 字段路径 -> default/agent/user；仅保护明确手填字段
  revision INT NOT NULL DEFAULT 0,           -- 草稿并发更新检查
  client_request_id VARCHAR(64),             -- 同用户创建草稿去重；联合唯一索引
  standard_version_id BIGINT,                -- 提交使用的不可变标准快照
  quality_content_hash CHAR(64),             -- 最终提交内容哈希
  status VARCHAR(16) NOT NULL DEFAULT 'DRAFT',  -- DRAFT/SUBMITTED/CLOSED
  submitter_id BIGINT NOT NULL,
  submitter_name VARCHAR(64), submitter_dept VARCHAR(128),  -- 提报时点快照（BR-R09）
  channel VARCHAR(32),
  session_id BIGINT,                         -- 产生该需求的 Agent 会话
  submitted_at DATETIME(3), closed_at DATETIME(3), close_reason VARCHAR(256),
  created_at, updated_at,
  UNIQUE (submitter_id, client_request_id),
  INDEX (submitter_id, status), INDEX (demand_type_code, status), INDEX (submitted_at)
)

-- 编号流水（按日按类型，行锁保证无空洞）
demand_no_seq(biz_date DATE, type_code VARCHAR(32), seq INT, PK(biz_date, type_code))

-- Agent 会话必须绑定本人草稿；V1 每份草稿一个会话
agent_session(id, session_no VARCHAR(64) UNIQUE, user_id, scene, demand_id BIGINT UNIQUE NOT NULL,
              title, status, asked_target VARCHAR(64), created_at, updated_at)
agent_message(id, session_id, role, content TEXT, structured_payload JSON,
              request_id VARCHAR(64), request_hash CHAR(64), prompt_version_id BIGINT,
              model VARCHAR(64), prompt_tokens INT, completion_tokens INT, latency_ms INT, created_at,
              UNIQUE(session_id, request_id, role))

-- 提示词/标准版本留痕（每次对话记录用的是哪个版本，便于回溯效果）
prompt_version(id, code VARCHAR(64), version VARCHAR(32), content_hash CHAR(64) UNIQUE,
               snapshot JSON, created_at)  -- 保存标准/模板原文和渲染规则版本，不只保存 hash
```

设计要点：
- `ext` 用 JSON 列替代类型扩展表。开发与测试基线为 MySQL 8；MySQL 5.7 已有原生 JSON，SQLAlchemy 不会自动退化为 TEXT。
- `quality` 快照是"整理"能力的数据基础：可以直接统计"提报需求中验收标准到位率"这类指标，这正是 BRD 成功度量里的"一次性受理通过率"前置数据。
- 不建 `demand_draft`：草稿就是 `status=DRAFT` 的 demand 行。
- 草稿创建、更新、提交分开校验；提交锁定该需求行，在同一事务内生成编号、保存最终质量/身份快照、关闭关联会话。重复提交已提交的同一需求返回已有结果，不能再次分配编号。并发更新校验 `revision`，不静默覆盖。

---

## 5. API 设计（前后端同步升级）

统一前缀 `/demandhub-api`。Kong `strip_path=false` 时服务实际路由也使用该前缀；`root_path` 不代替路由定义，直连与代理各验一次。响应体沿用 `{code, message, data}`，业务异常 HTTP 200 + `code≠0`，鉴权失败返回 HTTP 401；健康检查失败为 HTTP 503。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 平台健康检查（含 DB ping） |
| GET | `/standards` | 需求类型列表（code / name / 简介），登录即可读 |
| GET | `/standards/{type}` | 某类型的完整标准：要素、到位线、选项枚举、追问顺序、子类补充字段（§6.1 YAML 的 JSON 形态）。H5 用它渲染表单与完备度清单；后续 CLI / Skill 用它指导收集 |
| GET | `/auth/channel-sso?channel=&ticket=&state=` | 票据回源 → 建号/更新 → 签发 JWT（复用现有 H5 守卫） |
| POST | `/auth/dev-login` | **仅 `AUTH_DEV_LOGIN=true` 时注册**，本地/测试环境免依赖创金零售 |
| GET | `/auth/me` | 当前用户 |
| POST | `/agent/session` | 按 `demandId` 创建或返回本人草稿唯一会话（`scene=SUBMIT_GUIDE`） |
| GET | `/agent/session/list` | 我的会话 |
| GET | `/agent/session/{id}/messages` | 会话消息（恢复对话） |
| POST | `/agent/guide/chat/stream` | 请求含会话/草稿 ID、`requestId`、草稿 revision、字段来源。成功：message* → structured → done（最终结果已提交数据库）；流内失败：error 后关闭，不发送成功 done。开流前错误返回普通 JSON |
| POST | `/agent/guide/chat` | 非流式（调试/降级） |
| POST | `/demand` | 创建可不完整草稿，`clientRequestId` 按用户去重；返回 id/revision |
| PUT | `/demand/{id}` | 更新草稿 |
| POST | `/demand/{id}/submit` | 提交（**代码决策点**）：schema 闭集校验（枚举字段按选项校验，文本字段按长度校验）、title/type/content 必填；按标准对各要素做一次**服务端复判**（规则层：长度 / 歧义词 / 量化特征，不调模型），写入 `quality` 快照；生成编号、写提报人快照、状态 SUBMITTED。VAGUE/MISSING 允许提交，但记录在 `quality` 中供整理。所有渠道（H5 / 未来 CLI）提交都走此处，质量口径统一 |
| POST | `/demand/{id}/close` | 提报人撤销（BR-R02） |
| GET | `/demand/my?status=&page=` | 我的需求 |
| GET | `/demand/{id}` | 详情（含会话回放） |
| GET | `/demand/{id}/export.md` | 单条整理为 Markdown（含要素清单与对话摘要） |
| GET | `/admin/demand/list?type=&status=&from=&to=` | 白名单用户（`ADMIN_WECOM_USERIDS` env）查看全量 |
| GET | `/admin/demand/export.xlsx` | 全量导出（按类型分 sheet，含 `quality` 各要素状态列） |

共 19 个端点（现有 139 个）。其中 `/standards/*`、`/demand/*` 是"开放能力"面，与 H5 无关的客户端只依赖这两组 + `/auth`；`/agent/*` 是服务端托管的启发能力，客户端可用可不用（CLI / Skill 场景可由用户自己的 Agent 承担启发，只用 `/standards` 与 `/demand`）。

`api/agent.ts` 必须升级：识别 `error` 与非空 `done` payload，只有成功终态才视为完成；无 done 的 EOF 视为中断。消息使用 `requestId` 去重，同一 ID 不同输入返回冲突。不允许用忽略未知事件掩盖模型或数据库失败。

---

## 6. Agent 设计（MVP 的核心：模型判断、代码决策）

### 6.0 交互原则（H5 侧）

沿用并强化现有 `AgentGuideSheet.vue` 的"表单锚定"形态，不做纯聊天机器人：

| 原则 | 落地 |
|---|---|
| 表单是共享状态 | 表单 + 要素完备度清单常驻可见；模型产出只回填表单、更新清单；用户随时直接改表单，手填优先于 AI |
| 一次成型优先 | 首轮入口文案"随口说、粘一大段、语音输入都行"；首轮模型做整段抽取，输出草稿 + 缺口清单；多数情况用户补表单即可提交 |
| 追问是例外 | 只有阻塞要素（§6.1 `elements`）VAGUE/MISSING 时追问，一次一个，同一要素最多 2 次，第 2 次给句式模板，之后允许"后续补充"（SKIP） |
| 闭集用选项 | 类型 / 子类 / 紧急度一律 quickReplies 点选，模型不自由发挥，用户不自由输入 |
| 提交前必确认 | 草稿及对话自动保存；用户确认表单后点击提交，才生成正式编号和最终质量快照。正式提交不由模型触发 |

### 6.1 需求标准配置化

```yaml
# app/standards/tech.yaml
type: TECH
name: 科技需求
elements:                      # 阻塞式要素：不到位会追问（最多 2 次）
  - key: title
    label: 需求标题
    ok_when: 一句话，2~60 字，能看出要解决什么问题
  - key: content
    label: 需求描述
    ok_when: ≥10 字，含业务背景与期望效果
  - key: techSubtype
    label: 需求子类
    options: {SYS_DEV: 系统开发, DATA_RPT: 数据报表, SYS_INT: 系统集成, OPS_OPT: 运维优化, OTHER: 其他}
  - key: businessScenario
    label: 业务场景
    ok_when: 含角色 + 时机/频率 + 任务，≥15 字，无歧义词
    vague_hint: 看不出谁在用、什么时候用
    ask_l1: 记下了。不过「{snippet}」还有点概括——能再具体说说哪些人、在什么时机用吗？
    ask_l2: 可以这样写：「作为__（角色），在__（时间/频率），需要__（做什么）」。
    example: 机构业务部客户经理，每天晨会前查各机构持仓
  - key: acceptanceCriteria
    label: 验收标准
    ok_when: 含可量化指标（数字/时间/误差/通过率）或明确检查项
    ...
  - key: valueImpact
    label: 价值与影响
    ok_when: 含量化事实（多少人/多少时间/不做的后果）
    ...
follow_up_order: [techSubtype, businessScenario, acceptanceCriteria, valueImpact]
max_attempts: 2
vague_words: [尽快, 好用, 方便, 优化一下, 越快越好, 体验, 满意, 顺便]
skip_phrases: [不知道, 跳过, 后续补充, 再说吧, 不清楚, 先这样]
subtype_fields:                # 非阻塞补充要素：顺带抽取，不追问
  DATA_RPT: [dataDimensions, dataSource, refreshFrequency, exportRequirement]
  SYS_DEV:  [devFeatures, devPermission, devQuality]
  SYS_INT:  [intTargetSystem, intDataFlow, intTimeliness, intException]
  OPS_OPT:  [opsProblem, opsScope, opsTarget]
```

系统提示词由 `submit_guide.md` 和标准生成。标准接口、提示词和提交规则共享定义，但规则检查与模型语义判质不保证结论相同。`prompt_version.snapshot` 保存完整标准、提示词模板及渲染规则版本；消息关联本轮版本，正式记录关联提交版本及内容哈希，后续修改 YAML 不改变历史解释。

标准中的 `glossary` 随提示词注入，提供公司术语释义；未知事实保持缺失，不推断用户归属或需求目标。

### 6.2 模型与代码的分工

| 职责 | 归属 | 说明 |
|---|---|---|
| 抽取字段增量、语义判质 | 模型 | 输出闭集字段和 OK/VAGUE/MISSING；不决定提交、不生成追问 |
| 字段来源保护 | 代码 | `fieldSources` 按字段路径记录 default/agent/user；模型可修正 default/agent 值，不能覆盖 user 值，包括用户主动清空。用户直接修改后立即标 user |
| 要素集合与值校验 | 代码 | 以当前类型标准完整 key 集合为准；未知或重复 key 拒绝；遗漏要素用规则补齐；空值、非法枚举不得成为 OK |
| 下一追问及话术 | 代码 | 先合并本轮抽取、完成判质，再选目标，使用 YAML 的 ask_missing/ask_l1/ask_l2。实际发出的问题保存为 askedTarget |
| attempts 与跳过 | 代码 | 只对上一轮实际 askedTarget 计次；回答仍未到位才 +1，最多两次。明确跳过只作用于该目标；字段后来有新值则重新判质，不保留过期 SKIP |
| 三个完成标记 | 代码 | canSubmit=必填和格式有效；guidanceComplete=没有可追问目标；qualityComplete=所有要素 OK。SKIP 或次数耗尽不表示质量到位。ready 如保留仅为 canSubmit 的兼容别名 |
| quickReplies | 代码 | 闭集取标准选项；允许跳过时添加“后续补充”，不接受模型扩展枚举 |
| 编号、归属、事务与质量快照 | 代码 | 正式提交规则复判；模型完全不参与数据库决策 |

### 6.3 对话编排（单次请求流程）

1. 开流前校验身份、本人草稿、该草稿唯一会话、状态、revision 和 requestId。相同 requestId/输入重试返回已保存结果，不重复调用模型；不同输入返回冲突。
2. 加载完整草稿及字段来源、最近 20 条消息、上一轮保存的 askedTarget/要素。客户端先保存手改表单再发起对话，草稿是服务端唯一输入状态。
3. 渲染本轮标准与提示词快照；类型未知时只提供共用必填字段和类型选项。
4. 调方舟 stream=True/json_object，累计抽取 JSON；前端可显示 processing 状态，但不能把它算作首个可用答复。模型文本不作为最终追问。
5. 完整解析并校验输出；最多一次非流式修复。成功计数在完整解析与校验后清零，连续无效 JSON 也计入失败熔断。
6. 保护 user 字段，合并合法增量；如类型改变，按新标准过滤并判质。构建完整要素集合，重新评估变化的字段，计算 attempts/跳过。
7. 计算 canSubmit/guidanceComplete/qualityComplete；选择下一目标，按标准模板生成唯一追问及 quickReplies。
8. 在短事务内再次锁行校验 revision/状态，原子保存草稿、字段来源、revision、两条消息、askedTarget、完整响应及版本关联；模型等待期间不持有数据库行锁。
9. 提交事务成功后发送 message、structured，最后发送非空 done。断线发生于保存之后时，客户端用同一 requestId 重试恢复结果。
10. 流内失败发送 error 后关闭，不发送 done；保存前取消或失败不产生半条成功记录。禁止在生成器 finally 中补写成功记录。每会话并发互斥，数据库 revision 兜底防止手填/提交与模型结果互相覆盖。

### 6.4 模型选择

| 用途 | 建议 | 说明 |
|---|---|---|
| 提报对话 | **已定：方舟 DeepSeek V4 Pro**（现有 endpoint `ep-20260930122836-rv2gw`），`temperature 0.3`，`max_tokens 1500` | V4 Pro 是推理模型，交互延迟是 V1 最大体验风险。应对：① 请求带 `thinking: {type: "disabled"}`（方舟 OpenAI 兼容接口的扩展参数，若该 endpoint 支持则显著降低延迟）；② 上游流式抽取，前端显示处理状态；③ 读超时 60s；④ P4 分别记录首个处理状态、首个可用答复与单轮完成的 P50/P95。可用答复 P95 > 5s 或单轮 P95 > 20s 时记录结果并评估 endpoint，不能用占位事件冒充低延迟 |
| Embedding | 方舟已有 embedding endpoint（`ep-20260930123423-mq6hq`），**V1 不用** | 无存量数据，RAG 无意义；保留 env 位，二期相似需求推荐时启用 |
| 提交时的需求整理摘要（可选） | 同一模型 | 离线、不阻塞用户；V1 不做 |

模型 endpoint 全部 env 注入（`LLM_CHAT_MODEL` / `LLM_EMBEDDING_MODEL` / `LLM_THINKING`），切换零代码。

### 6.5 评测集

`tests/eval/cases/*.yaml` 约 20 条多轮对话，每条给定用户输入序列与期望（抽取字段、各要素状态、代码应选的追问目标、是否 ready）。来源：`MockLlmClient` 的规则用例、`phase7_selftest.py` 的检查点。分两层：

- **代码层（无需 API Key，CI 必跑）**：mock 模型输出，验证 §6.2 全部代码决策规则（追问目标选择、attempts、SKIP、ready、手填优先、枚举校验）
- **模型层（`@eval`，需 API Key，改提示词/标准必跑）**：真实调用，只评"抽取准确率"与"要素判质一致率"两项，通过线 ≥ 80%

---

## 7. 认证与安全

- **交付形态（已定）**：产物是一个 H5，嵌入创金零售小程序/企微应用内打开；MVP 用户全部从创金零售入口进入。沿用一次性 ticket → `GET /auth/channel-sso` 回源 verify → 建号（`wecom_userid` 匹配）→ JWT。契约、签名、错误码、熔断逐行移植自 Java 版，单测用例同步移植。若宿主为真小程序 web-view，需创金零售侧把 H5 域名加入业务域名白名单；H5 不依赖任何 JS-SDK，返回按钮行为可配置（`history.back()` 或关闭提示）。
- **开发/测试**：`AUTH_DEV_LOGIN=true` 时开放 `/auth/dev-login`（输入 name + wecom_userid），生产必须 false；契约 Mock 用现有 `contract_mock_verify.py`。
- **JWT**：HS256，`JWT_SECRET` env 注入，access 8h，无 refresh、无服务端会话（无 Redis）。注销即前端清 token；每次请求校验数据库用户 ACTIVE 状态，管理员身份按当前用户和配置判断。
- **数据权限（已定：V1 最小化）**：提报人只能读写自己的需求；`/admin/*` 按 `ADMIN_WECOM_USERIDS` 白名单（env 逗号分隔，为空则 admin 接口全部 403）。无角色表、无组织范围，实现完再看。
- **密钥**：全部 env 注入；JWT_SECRET 及生产 SSO 配置缺失时启动失败。LLM_API_KEY 缺失时仅 Agent 返回 1401，独立需求 API 与手填流程仍可用。日志中 ticket / phone 脱敏（移植 `SsoSignUtil.maskTicket/maskPhone`）。
- **Agent 隐私（已确认 OK）**：对话内容送方舟已通过公司合规确认；送模型前不做额外脱敏。

---

## 8. 项目结构

```
DemandHub/
├── server/                          # 新：Python 后端（backend-image-push 在此目录运行）
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── .env.example
│   ├── alembic.ini
│   ├── alembic/versions/0001_init.py
│   ├── app/
│   │   ├── main.py                  # FastAPI 实例、实际路径前缀、路由挂载
│   │   ├── config.py                # Settings（含 DATABASE_URL 解析）
│   │   ├── core/                    # result.py（统一响应）、errors.py（错误码）、security.py（JWT）、deps.py
│   │   ├── db/                      # session.py、models.py
│   │   ├── api/                     # health.py、standards.py、auth.py、agent.py、demand.py、admin.py
│   │   ├── standards/               # tech.yaml / matl.yaml / train.yaml + loader.py + rules.py（规则层判质，submit 复判与 MISSING 硬校验共用）
│   │   ├── agent/
│   │   │   ├── llm_client.py        # 方舟客户端（流式 + 冷却降级）
│   │   │   ├── guide.py             # 对话编排（§6.3）
│   │   │   ├── policy.py            # 代码决策：pickFollowUp / attempts / SKIP / ready / quickReplies（§6.2）
│   │   │   ├── schemas.py           # GuideResult / ElementStatus（Pydantic）
│   │   │   └── prompts/submit_guide.md
│   │   ├── sso/                     # chuangjin_ls.py、sign.py、schemas.py
│   │   └── services/                # demand_service.py、demand_no.py、export.py
│   └── tests/
│       ├── test_sso.py              # 移植自 Java 单测
│       ├── test_llm_client.py
│       ├── test_policy.py           # 代码决策规则（mock 模型输出，CI 必跑）
│       ├── test_standards_rules.py  # 规则层判质
│       ├── test_demand.py
│       ├── contract_mock.py         # 复用
│       └── eval/                    # 提示词评测集（需 API Key）
├── frontend/h5/                     # 裁剪：保留 auth / report / mine / demand-detail
├── frontend/pc/                     # 开发期不动；上线后删除
├── backend/                         # Java 版：开发期不动；上线后删除
├── deploy/                          # 新增 docker-compose.dev.yml（仅 mysql + contract-mock）；旧编排上线后删除
├── scripts/                         # 新增 e2e_mvp.py；旧 phase*.py 上线后删除
└── *.md                             # 设计文档保留
```

**Dockerfile（符合 backend-image-push 规则：只跑业务进程，MySQL 走 env）**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Shanghai
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN useradd -r -u 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
```

**环境变量清单**

| 变量 | 必填 | 说明 |
|---|---|---|
| `DEMANDHUB_DATABASE_URL` | 是 | 平台下发 `mysql://user:pass@host:port/db` |
| `JWT_SECRET` | 是 | ≥32 字符 |
| `LLM_API_KEY` / `ARK_BASE_URL` / `LLM_CHAT_MODEL` | Agent 必需 | 未配置 Key 时保留手填能力；方舟；`LLM_CHAT_MODEL` 默认 `ep-20260930122836-rv2gw`（DeepSeek V4 Pro） |
| `LLM_THINKING` | 否 | 取值 `disabled` / `enabled` / `auto`；设置时随请求传 `thinking: {type}`，不设则不传 |
| `LLM_READ_TIMEOUT_S` | 否，默认 60 | 单轮读超时 |
| `LLM_EMBEDDING_MODEL` | 否 | V1 不用，预留 |
| `CHANNEL_LS_BASE_URL` / `CHANNEL_LS_APP_KEY` / `CHANNEL_LS_APP_SECRET` | 生产必填 | 创金零售 verify |
| `AUTH_DEV_LOGIN` | 否，默认 false | 仅 dev/test 为 true |
| `ADMIN_WECOM_USERIDS` | 否 | 逗号分隔 |
| `API_ROOT_PATH` | 否，默认 `/demandhub-api` | Kong 路径前缀 |

---

## 9. H5 裁剪方案

保留并复用（约 2.5k 行）：

| 文件 | 处理 |
|---|---|
| `components/AgentGuideSheet.vue` | 改为草稿会话绑定、字段来源保护、服务端完整要素渲染及 SSE 成败终态 |
| `views/report/index.vue` | 保留；表单字段与子类补充字段改为由 `GET /standards/{type}` 驱动渲染（不再硬编码）；删除代办提报字段（如有）；提交后跳转详情 |
| `views/mine/index.vue` | 保留；状态筛选缩为 3 态 |
| `views/demand/detail.vue` | 大幅精简：只展示需求字段 + 要素完备度 + 会话回放 + 撤销按钮；删除评论/附件/方案/工时/流转日志 |
| `views/auth/index.vue`、`router/index.ts` 守卫 | 改造：hash 路由初始化前读取外层 location.search 的 ticket/from；兼容 hash query，登录后清除一次性票据 |
| `api/request.ts`、`api/agent.ts`、`api/auth.ts`、`api/demand.ts` | 同步升级 §5 契约，移除 refresh；导出用带 Bearer 的 fetch 获取 Blob |
| `store/user.ts` | 保留 |
| `views/notification/*`、`views/triage/*`、`views/demand/acceptance.vue`、`store/notification.ts`、`api/notification.ts`、`api/directory.ts`、`components/UserPicker.vue`、`AppLayout` 中的 tabbar 通知项 | 删除 |

新增 `views/admin/index.vue`：按类型/状态/日期筛选全量需求、查看详情和导出；入口仅对白名单管理员显示，服务端独立鉴权。报告页保留“保存草稿”，首次保存或启用 Agent 即创建草稿并绑定唯一会话，重进恢复草稿；类型默认值标 default，用户修改标 user。

两处适配 `h5-package-build` 规则：
1. **路由 base 去硬编码**：改为 `createWebHashHistory()`（最简，天然与 `/h5/<route-key>/` 和 `/h5-preview/<route-key>/` 无关），或按 skill 建议运行时从 `location.pathname` 推导 basename。推荐 hash 路由。
2. **API 前缀**：`VITE_API_BASE=/demandhub-api`，`vite.config.ts` `base: './'`（相对资源路径）。

---

## 10. 实施计划（约 10～12 个工作日）

| 阶段 | 工期 | 交付物 | 验收 |
|---|---|---|---|
| **P0 决策冻结** | 已完成 | 见 §11 决策记录 | — |
| **P1 骨架 + 部署通路打通** | 1d | FastAPI 骨架、`/health`、Dockerfile、Alembic 0001；H5 空壳 zip | `backend-image-push` 推镜像成功并在平台起来，`/demandhub-api/health` 200；`h5-package-build` 产物可在 `/h5-preview/` 打开。**先打通本地容器构建与路径验证；外部平台配置具备后部署验收**，记录平台验收待办 |
| **P2 认证** | 1d | SSO 移植 + 单测、dev-login、JWT、`/auth/me` | `tests/test_sso.py` 全绿（含契约 Mock 严格验签）；H5 守卫携 ticket 免登 |
| **P3 标准与开放能力** | 1.5d | 标准 YAML ×3 + loader + 规则层判质、`GET /standards/*`、demand CRUD、编号、`submit` 复判与 quality 快照、我的需求、详情 | 不经 Agent、直接调 API 可完成"建草稿 → 提交 → 查询"闭环；并发提交编号无重复；代码层测试全绿 |
| **P4 Agent 启发** | 3d | 提示词模板、方舟流式客户端、`policy.py` 代码决策、编排、会话/消息落库、SSE 端点、评测集 20 条 | 草稿隔离、手改保护、计次和 SSE 失败用例通过；真实模型评测 ≥80%，输出延迟实测报告 |
| **P5 H5 裁剪 + 整理导出** | 2d | 按 §9 删减、表单由标准驱动、hash 路由、API 前缀、打包；md/xlsx 导出、admin 列表 | 真机（iOS/Android 各 1）提报全流程；zip 校验无 blocked file；xlsx 含要素状态列 |
| **P6 联调上线** | 1～2d | 测试环境全链路（含创金零售 verify 测试地址）、e2e 脚本（Python，沿用 `scripts/phaseX` 风格）、上线 checklist | 从创金零售入口跳入 → 对话 → 提交 → 我的需求可见 → admin 导出 |
| *P7 CLI / Skill 客户端（V1 之后）* | *1～2d* | *`demandhub` CLI（`standards show` / `demand create` / `demand submit`）+ SKILL.md（指导用户 Agent 先读标准再收集再提交）* | *不在 V1 范围；API 稳定后按需启动* |
| **P8 上线后清理** | 0.5d | 上线稳定 ≥3 个工作日后删除 `backend/`、`frontend/pc/`、旧 `deploy/*.yml` 与 `deploy/h5pub/`、`deploy/mysql/`、`deploy/rocketmq/`、`scripts/phase*.py`、`scripts/shots/`；更新 README | 仓库只剩 `server/`、`frontend/h5/`、`deploy/docker-compose.dev.yml`、`scripts/e2e_mvp.py`、文档 |

顺序上把 P3（标准 + 开放能力）放在 P4（Agent）之前，是为了让"开放能力"先独立成立、Agent 作为增强叠加上去，与设计原则 5 一致。

里程碑：P1 结束即有"可部署空壳"；P3 结束即有可用的 API（可用 curl 提需求）；P4 结束即可内部试用 Agent 对话（dev-login）；P6 结束上线。

---

## 11. 决策记录（2026-09-30 冻结）

| # | 问题 | 决策 | 对方案的影响 |
|---|---|---|---|
| 1 | 仓库策略 | **同仓**新增 `server/`，不新建仓库 | `backend-image-push` 需显式 `--repository retail/demandhub-api`（git remote 推断出的名字是 `demandhub`，不用它）；构建上下文为 `server/` |
| 2 | 模型 | 对话用方舟 **DeepSeek V4 Pro**（现有 endpoint）；方舟另有 embedding endpoint | V1 不用 embedding；V4 Pro 为推理模型，按 §6.4 四项措施控延迟，P4 实测后决定是否换 endpoint |
| 3 | 登录形态 | MVP 全部从**创金零售**进入；交付物是 **H5，嵌入创金零售小程序** | SSO 票据链路照移植；dev-login 仅本地；需确认小程序 web-view 业务域名白名单 |
| 4 | 权限 | **暂不做**复杂权限，实现完再看 | 仅"本人可见 + admin 白名单 env" |
| 5 | Agent 隐私 | **已确认 OK** | 不做额外脱敏 |
| 6 | Java 版处置 | 上线后**删除** | 增 P8 清理任务；开发期 `backend/` 不动 |

---

## 12. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| DeepSeek V4 Pro 推理延迟高 | 交互式追问体验差 | `thinking: disabled` + 真流式 + 读超时 60s + "正在思考"提示（§6.4）；P4 实测 P95，超标记录证据并确认 endpoint 调整 |
| 模型输出格式漂移 | 当前轮不能完成 | 完整校验后最多修复一次；失败 error 终止，前端保留输入供同 requestId 重试，不冒充成功 |
| 模型不遵守 JSON 契约 | 字段丢失 / 状态非法 | Pydantic 严格校验 + `normalizeStatus` 归一 + 重试 1 次 + 代码后处理（§6.2） |
| 上下文不足导致模型对同一需求给出不同处理 | 记录不稳定、用户不信任 | 记录路径完全不经模型（§0 原则 1）；每轮输入全部确定性注入（§2）；闭集枚举 + 手填优先 + 提交前确认；模型仍可能误抽取/误判，靠评测和用户确认约束 |
| 纯对话填表体验反直觉（不知道要什么、改不了早先说的、看不见结果） | 用户回到微信群提需求 | 表单锚定 + 一次成型优先（§6.0）；完备度清单常驻；随时可弃用 Agent 纯手填 |
| 创金零售 verify 测试环境未就绪 | 阻塞 SSO 联调 | dev-login + 契约 Mock 先跑通全流程；SSO 逻辑逐行移植并有单测，联调只剩配置 |
| 平台 MySQL 与测试版本不一致 | 迁移或锁行为差异 | 验收基线 MySQL 8；上线前确认平台版本并跑迁移。MySQL 5.7 有原生 JSON，不存在自动退化为 TEXT 的保证 |
| 平台单容器无持久化本地盘 | 无影响 | 设计上无本地状态；导出为流式响应不落盘 |
| 后续要长回分派/SLA 等能力 | 二次投入 | `demand.status` 与编号规则已与一期蓝图对齐；`ext`/`quality` JSON 可平滑迁入扩展表；届时按真实数据决定做什么 |

---

## 13. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| v1.3 | 2026-09-30 | 统一不完整草稿、字段来源、草稿唯一会话、askedTarget、三种完成标记、提交幂等与 revision、先落库后 SSE 终态、标准快照及 H5 管理导出；修正 hash 登录、数据库与容器运行契约 |
| v1.0 | 2026-09-30 | 初稿；基于 `main@783c80f`（含 RealLlmClient 与 P11 提示词）编制 |
| v1.2 | 2026-09-30 | 六项决策冻结（§11 改为决策记录）：同仓 `server/`；DeepSeek V4 Pro + thinking 控制；H5 嵌创金零售小程序；权限最小化；隐私已确认；上线后删除 Java（新增 P8）。配套产出实施计划文档 |
| v1.1 | 2026-09-30 | 按第一性原理讨论修订：§0 增设计原则五条（模型判断/代码决策、schema 闭集、表单锚定、一次成型优先、API-first 标准即资源）；§2 架构改为 headless + 薄客户端，补上下文确定性说明；§5 增 `GET /standards/*`、`submit` 改为服务端复判点（19 端点）；§6 新增 6.0 交互原则与 6.2 模型/代码分工表，编排流程加入代码预判与后处理；§8 增 `standards/` 与 `policy.py`；§10 调整为标准与开放能力先于 Agent，增 P7 CLI/Skill（V1 后）；§12 增两条风险 |
