# DemandHub · Python 改造实施计划（供执行方使用）

| 项目 | 内容 |
|---|---|
| 版本 | v1.1 |
| 日期 | 2026-09-30 |
| 上游文档 | `DemandHub_Python重构方案_MVP_v1.0.md` v1.3（以下称"方案"）；本计划不重复方案中的论证，只写"做什么、怎么做、做到什么程度算完" |
| 基线 | `main@783c80f` |
| 执行者 | 代码由 GPT 6.1 Sol high Subagent 实现；主 Agent 负责审计和验收 |

---

## 0. 执行者必读

### 0.1 你要做的事

在现有仓库中新增 `server/`（Python FastAPI 后端），裁剪 `frontend/h5/`，使二者组成一个可通过公司发布平台上线的最小需求收集系统。**不要修改 `backend/`、`frontend/pc/`、现有 `deploy/docker-compose*.yml`（允许新增 dev 编排）、`deploy/mysql/`、`deploy/h5pub/`、`scripts/phase*.py`**——它们是 Java 版，上线后统一删除（任务 P8），开发期只读、只作为移植参考。

### 0.2 硬约束

1. **平台规则**（来自 `~/.agents/skills/backend-image-push/SKILL.md` 与 `h5-package-build/SKILL.md`）：
   - 后端镜像只跑业务进程；MySQL 由平台提供，只经 `DEMANDHUB_DATABASE_URL` 注入；不得在镜像内起 Redis / MQ / Nginx
   - 后端对外路径前缀 `/demandhub-api`，禁止使用 `/api`、`/health`、`/docs`、`/admin` 等通用前缀作为公开路径；健康检查为 `/demandhub-api/health`
   - H5 zip 根目录必须有 `index.html`；资源相对路径；不得硬编码 `/h5/xxx` 路由 base；不打包 `.env`、脚本、密钥
   - H5 中 API 地址用服务专属公开路径 `/demandhub-api/...`，不得指向 localhost / 容器名 / 临时端口
2. **模型判断、代码决策**（方案 §0 原则 1、§6.2）：任何"决定"（追问哪个要素、attempts、SKIP、ready、写库、编号）都必须在 Python 代码中实现并有单测，不得依赖模型输出
3. **密钥零入库**：`.env.example` 入库，`.env` 不入库；测试用假密钥写在测试文件里
4. **中文注释与日志**：与现有仓库风格一致；日志中 ticket、手机号必须脱敏
5. **所有任务的验收命令必须能在 `server/` 目录下一条命令跑通**：`uv run pytest`（不含 `@eval`）必须全绿才能进入下一任务

### 0.3 工具链

- Python 3.12：`uv python pin 3.12`，`requires-python = ">=3.12,<3.13"`，本地与容器一致
- 包管理：`uv`（`uv init`、`uv add`、`uv sync`、`uv run`）
- 本地 MySQL：任务 P1 新增 `deploy/docker-compose.dev.yml`（mysql:8.0 端口 3308 + contract-mock 8099），不复用旧编排
- Node 18+（H5）

### 0.4 移植参考索引（Java → Python）

执行时按此表打开对应 Java 文件逐段翻译；不要凭记忆重写。

| 能力 | Java 源 | 目标 Python 文件 |
|---|---|---|
| 统一返回体 / 错误码 | `backend/demandhub-common/.../core/Result.java`、`ErrorCode.java` | `server/app/core/result.py`、`errors.py` |
| 全局异常 → HTTP 200 + code | `backend/demandhub-common/.../exception/GlobalExceptionHandler.java` | `server/app/core/exceptions.py` |
| DATABASE_URL 解析 | `backend/demandhub-common/.../config/DatabaseUrlEnvironmentPostProcessor.java` | `server/app/config.py` |
| SSO 签名 / 脱敏 | `backend/demandhub-system/.../sso/SsoSignUtil.java` | `server/app/sso/sign.py` |
| SSO 客户端（verify、错误码映射、熔断） | `backend/demandhub-system/.../sso/ChuangjinLsSsoClient.java` | `server/app/sso/chuangjin_ls.py` |
| SSO 客户端单测（14 个用例） | `backend/demandhub-system/src/test/.../sso/ChuangjinLsSsoClientTest.java` | `server/tests/test_sso_client.py` |
| verify 契约 Mock | `deploy/h5pub/contract-mock/contract_mock_verify.py` | 复制到 `server/tests/contract_mock.py`（不改逻辑） |
| 方舟 LLM 客户端 | `backend/demandhub-agent/.../llm/RealLlmClient.java` | `server/app/agent/llm_client.py` |
| LLM 客户端单测（相关 5 个用例） | `backend/demandhub-agent/src/test/.../llm/RealLlmClientTest.java` | `server/tests/test_llm_client.py` |
| 代码决策规则（pickFollowUp / attempts / SKIP） | `backend/demandhub-agent/.../llm/MockLlmClient.java` 中 `pickFollowUp`、`buildStatus`、`evaluate*`、`quickRepliesFor`、`TECH_ELEMENT_ORDER`、`VAGUE_WORDS` | `server/app/agent/policy.py`、`server/app/standards/rules.py`、`server/app/standards/tech.yaml` |
| 提示词 | `deploy/mysql/init/09-ark-llm-prompt.sql` 中 `SUBMIT_GUIDE` 的 content | `server/app/agent/prompts/submit_guide.md`（按 §3.5 改造） |
| 需求编号规则 | `backend/demandhub-demand/.../service/DemandNoGenerator.java` | `server/app/services/demand_no.py` |
| 会话 / 消息表结构 | `deploy/mysql/init/05-schema-m6m9.sql` 的 `agent_session`、`agent_message` | `server/alembic/versions/0001_init.py` |
| 需求表字段取舍 | `deploy/mysql/init/01-schema.sql` 的 `demand`、`demand_ext_tech` | 同上（按方案 §4 精简） |
| 子类补充字段清单 | `frontend/h5/src/views/report/index.vue` 的 `ExtForm` 接口与各子类 `van-field` | `server/app/standards/tech.yaml` 的 `subtype_fields` |

---

## 1. 目标目录结构

```
server/
├── Dockerfile
├── .dockerignore
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md                         # 本地启动 / 测试 / 构建推送三段
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/0001_init.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── core/
│   │   ├── result.py                 # ok() / fail()；Result 模型
│   │   ├── errors.py                 # ErrorCode 枚举 + BizError 异常
│   │   ├── exceptions.py             # 注册到 FastAPI 的异常处理器
│   │   ├── security.py               # JWT 签发 / 解析
│   │   └── deps.py                   # get_db / get_current_user / require_admin
│   ├── db/
│   │   ├── session.py                # async engine / sessionmaker
│   │   └── models.py                 # 6 张表的 SQLAlchemy 模型
│   ├── standards/
│   │   ├── __init__.py
│   │   ├── loader.py                 # 读 YAML → Standard 对象；缓存；content_hash
│   │   ├── schema.py                 # Standard / Element 的 Pydantic 定义
│   │   ├── rules.py                  # 规则层判质：assess(standard, form) -> list[ElementStatus]
│   │   ├── tech.yaml
│   │   ├── matl.yaml
│   │   └── train.yaml
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── schemas.py                # GuideResult / ElementStatus / GuideChatRequest
│   │   ├── llm_client.py             # ArkClient：stream_json() / 冷却降级
│   │   ├── policy.py                 # 代码决策：pick_follow_up / merge_elements / decide_ready / quick_replies
│   │   ├── guide.py                  # 编排：一次对话的完整流程（方案 §6.3）
│   │   └── prompts/
│   │       └── submit_guide.md
│   ├── sso/
│   │   ├── __init__.py
│   │   ├── sign.py
│   │   ├── schemas.py                # SsoProfile / ChannelSsoConfig
│   │   └── chuangjin_ls.py
│   ├── services/
│   │   ├── user_service.py           # 建号 / 更新 / 查询
│   │   ├── demand_service.py         # 草稿 / 提交 / 撤销 / 查询
│   │   ├── demand_no.py
│   │   ├── session_service.py        # agent_session / agent_message
│   │   └── export.py                 # Markdown / xlsx
│   └── api/
│       ├── __init__.py               # 汇总 router
│       ├── health.py
│       ├── standards.py
│       ├── auth.py
│       ├── agent.py
│       ├── demand.py
│       └── admin.py
└── tests/
    ├── conftest.py                   # MySQL 8 测试库（见 §2.1）、client fixture
    ├── contract_mock.py
    ├── test_config.py
    ├── test_sso_sign.py
    ├── test_sso_client.py
    ├── test_auth_api.py
    ├── test_standards_loader.py
    ├── test_standards_rules.py
    ├── test_policy.py
    ├── test_llm_client.py
    ├── test_guide.py
    ├── test_demand_service.py
    ├── test_demand_api.py
    ├── test_export.py
    └── eval/
        ├── conftest.py               # 无 LLM_API_KEY 时整体 skip
        ├── cases/*.yaml
        └── test_eval_guide.py
```

---

## 2. 全局契约（所有任务共同遵守）

### 2.1 测试数据库

单测默认用 **MySQL 8 容器**（`deploy/docker-compose.dev.yml` 中的 `mysql`，库名 `demandhub_test`），通过 `TEST_DATABASE_URL` 注入；pytest 默认 `-m "not eval"`；`conftest.py` 在 session 开始时 `alembic upgrade head`，普通测试事务隔离；并发/事务提交测试使用独立连接并显式清理，仅允许测试库。不使用 SQLite（JSON 列与行锁语义不同，会掩盖问题）。

### 2.2 统一返回体

```json
{"code": 0, "message": "success", "data": <any>}
```

- 成功：HTTP 200，`code=0`
- 业务错误：HTTP 200，`code≠0`（沿用 Java 语义，前端 `request.ts` 依赖此行为）
- 未登录 / token 无效：**HTTP 401** 且 body 为 `{"code":401,"message":"未登录或登录已过期","data":null}`
- 参数校验失败（Pydantic `RequestValidationError`）：HTTP 200，`code=400`，`message` 为首个错误的 `loc + msg`
- 未捕获异常：HTTP 200，`code=500`，`message="系统内部错误"`，服务端记录堆栈

### 2.3 错误码（子集，保持与 Java 一致的数值）

| 常量 | code | message |
|---|---|---|
| SUCCESS | 0 | success |
| PARAM_INVALID | 400 | 参数校验失败 |
| UNAUTHORIZED | 401 | 未登录或登录已过期 |
| FORBIDDEN | 403 | 无权限访问 |
| NOT_FOUND | 404 | 资源不存在 |
| CONFLICT | 409 | 数据已更新或请求标识冲突 |
| SYSTEM_ERROR | 500 | 系统内部错误 |
| ILLEGAL_STATE_TRANSITION | 1001 | 非法的状态流转 |
| DEMAND_NOT_FOUND | 1002 | 需求不存在 |
| AUTH_SERVICE_UNAVAILABLE | 1102 | 身份服务暂不可用，请稍后重试 |
| CHANNEL_TICKET_INVALID | 1107 | 登录票据无效或已过期，请从原渠道重新进入 |
| CHANNEL_DISABLED | 1108 | 该渠道已停用 |
| CHANNEL_ACCOUNT_UNAVAILABLE | 1113 | 账号不可用，请联系管理员 |
| DEMAND_TYPE_INVALID | 1207 | 需求类型无效 |
| AI_SERVICE_UNAVAILABLE | 1401 | AI 服务暂不可用 |
| AGENT_SESSION_NOT_FOUND | 1402 | 会话不存在 |

`BizError(code: ErrorCode, message: str | None = None)`，`message` 缺省取枚举文案。

### 2.4 JWT

- HS256，`JWT_SECRET`（≥32 字符，启动校验）
- claims：`sub`（用户 id 字符串）、`uid`（wecom_userid）、`name`、`channel`、`iat`、`exp`（`iat + JWT_ACCESS_TTL_HOURS`，默认 8h）、`jti`（uuid4）
- `Authorization: Bearer <token>`；无服务端会话；不做 refresh
- `get_current_user` 依赖：解析成功后从 `dh_user` 读取用户，`status != ACTIVE` 视为 401

### 2.5 日期时间

- 数据库 `DATETIME(3)`，存 Asia/Shanghai 本地时间（与 Java 版一致，容器 `TZ=Asia/Shanghai`）
- API 输出 `YYYY-MM-DD HH:mm:ss`（`DATETIME`）与 `YYYY-MM-DD`（`DATE`）字符串，Pydantic `json_encoders` 统一
- 字段命名：API 一律 **camelCase**（与现有 H5 一致），数据库 snake_case；用 Pydantic `alias_generator=to_camel` + `populate_by_name=True`

### 2.6 前后端共同升级的草稿与对话契约

- 草稿 `POST /demand`：`clientRequestId` 必填；title/demandTypeCode/content 可空，编号为 null。相同用户同 ID 同输入返回同一草稿；不同输入返回 code=409。允许 declared 字段及 `fieldSources`，禁止赋值身份、状态、编号、quality。
- 更新 `PUT /demand/{id}`：`expectedRevision` + 表单字段 + `fieldSources`；手动修改（包括清空）写 user 来源，模型更新由服务端写 agent，初始化默认值才为 default。未声明来源的非空外部输入按 user。响应提供完整草稿和新 revision。
- `fieldSources` 是路径映射（如 `ext.businessScenario: user`）；用户字段不能被客户端伪造来源降级而默默覆盖。保留明确直接修改能力，不做自动解除保护。
- 提交 `POST /demand/{id}/submit`：`expectedRevision` 必填；重复提交已 SUBMITTED 的同一记录返回原结果。其余状态/旧 revision 拒绝。必填非空、所有提供字段满足类型/枚举/长度约束，质量不足本身不阻止提交。
- 创建会话 `POST /agent/session`：`demandId` 必填，`scene=SUBMIT_GUIDE`，创建或返回本人草稿唯一会话。聊天 `GuideChatRequest{demandId, sessionId, requestId, revision, message}`；客户端先保存表单，再发送当前 revision。服务端从数据库读取表单和字段来源，不信任游离 formContext。
- Agent 成功保存时 revision 增加；同 requestId 相同输入重试优先读取已保存响应，即使传入的是原 revision 也可恢复；同 ID 不同输入返回409。会话重复请求不得重复问模型或增加 attempts。

SSE 成功顺序（processing 可选，message 可以一条完整文本）：

```text
event: processing
data: {"requestId":"...","status":"processing"}

event: message
data: {"delta":"已保存的摘要与代码生成的追问"}

event: structured
data: {"demandId":1,"sessionId":1,"requestId":"...","revision":2,"structured":{},"fieldSources":{},"missing":[],"elements":[],"askedTarget":null,"canSubmit":true,"guidanceComplete":true,"qualityComplete":false,"ready":true,"quickReplies":[]}

event: done
data: {"requestId":"...","status":"completed"}
```

成功 message/structured/done 均在事务提交之后发送。流内失败：`event: error`，data 为 `{code,message,requestId}`，随后关闭，**不发送 done**。开流前不可用/鉴权/参数错误返回普通 JSON。`Content-Type: text/event-stream`，`Cache-Control: no-cache`，`X-Accel-Buffering: no`。

H5 只有收到有效 structured 和匹配的 completed done 才视为成功；error、无 done 的 EOF、解析失败或取消均终止等待，保留输入和 requestId 供重试，不产生空成功消息。重试保存成功但响应中断的请求可恢复已保存结果。

### 2.7 模型输出与服务器结果

模型只返回 `structured` 字段增量和 `elements[{key,status,note}]`；可附简短陈述摘要，但不得发问或声称提交/保存成功。模型 `status` 只接受 OK/VAGUE/MISSING；未知状态归 VAGUE，attempts/SKIP/ready/quickReplies 均不采信。

`structured` 使用明确闭集 DTO，当前类型 fields/optional/subtype/common 由标准声明；日期 YYYY-MM-DD、number 为合法数值，紧急度只能 NORMAL/URGENT/CRITICAL。未知字段过滤，已知字段错误值拒绝进入草稿。elements 以标准完整 key 集合为准，未知/重复 key 视为格式错误；缺失 key 用规则补齐，禁止空列表误判全到位。

响应中 `ElementStatus` 增加 label、attempts（用于展示），actual `askedTarget` 单独持久化。三个布尔值分别表示：canSubmit（必填及格式有效）、guidanceComplete（无可问目标）、qualityComplete（全部要素 OK）；ready 仅为 canSubmit 的兼容别名。达到次数上限/跳过不会把质量变为 OK。

### 2.8 需求标准 YAML schema

```yaml
type: TECH                         # 与 demandTypeCode 一致
name: 科技需求
version: "1"                       # 人工维护，改动标准时递增
glossary:                          # 领域词表，注入提示词
  - 代销系统：面向银行/券商等代销渠道的销售与结算系统
  - 晨会：一线部门每个交易日 8:30 前的例会
elements:                          # 质量要素（有序；required 控制必填，其他仅引导）
  - key: title
    label: 需求标题
    kind: text                     # text | enum | number | date
    required: true                 # 进入 missing 的三个关键字段 required=true
    ok_when: 一句话，2~60 字，能看出要解决什么问题
    rule:                          # 规则层判质（rules.py 使用；可选）
      min_len: 2
      max_len: 60
  - key: demandTypeCode
    label: 需求类型
    kind: enum
    required: true
    options: {TECH: 科技需求, MATL: 物料需求, TRAIN: 培训需求}
  - key: content
    label: 需求描述
    kind: text
    required: true
    ok_when: ≥10 字，含业务背景与期望效果
    rule: {min_len: 10}
    vague_hint: 描述过短，缺业务背景与期望效果
  - key: techSubtype
    label: 需求子类
    kind: enum
    path: ext.techSubtype          # 在 structured/表单中的位置；缺省为顶层 key
    options: {SYS_DEV: 系统开发, DATA_RPT: 数据报表, SYS_INT: 系统集成, OPS_OPT: 运维优化, OTHER: 其他}
    ask_l1: 为了把需求记录清楚，这个科技需求更接近哪一类？
  - key: businessScenario
    label: 业务场景
    kind: text
    path: ext.businessScenario
    ok_when: 含角色 + 时机/频率 + 任务，≥15 字，无歧义词
    rule:
      min_len: 15
      any_of: [每天, 每周, 每月, 每次, 当, 时, 晨会, 月底, 季, 客户经理, 理财经理, 专员, 机构, 营业部, 部门, 经理, 同事]
    vague_hint: 看不出谁在用、什么时候用
    ask_missing: 再说说使用场景吧：谁（角色）、在什么时间/频率、用它来做什么？比如「机构业务部客户经理，每天晨会前查各机构持仓」。
    ask_l1: 记下了。不过「{snippet}」还有点概括——能再具体说说哪些人、在什么时机用吗？
    ask_l2: 可以这样写：「作为__（角色），在__（时间/频率），需要__（做什么）」。示例：作为机构业务部专员，每周一早上，需要汇总各渠道销量。
  - key: acceptanceCriteria
    label: 验收标准
    kind: text
    path: ext.acceptanceCriteria
    ok_when: 含可量化指标（数字/时间/误差/通过率）或明确检查项
    rule:
      any_of_regex: ['\d', 误差, 对账, 通过率, 准确率, 检查, 为准, 一致]
    vague_hint: 缺可量化的验收指标
    ask_missing: 怎样算这个需求做完了？给一个可检查的标准，比如「连续一周与核心系统对账误差为0」。
    ask_l1: 「{snippet}」还不太可检验——能加个量化指标吗？比如时间、准确率或覆盖范围。
    ask_l2: 参考句式：「当__时，系统应__；检查项：①__②__」。
  - key: valueImpact
    label: 价值与影响
    kind: text
    path: ext.valueImpact
    ok_when: 含量化事实（多少人/多少时间/不做的后果）
    rule:
      any_of_regex: ['\d', 不做, 否则, 影响, 风险]
    vague_hint: 缺量化事实（人数/时长/后果）
    ask_missing: 这个需求不做的话有什么影响？量化一下，比如「20多个客户经理每人每天花40分钟手工整理」。
    ask_l1: 再具体一点点：大概影响多少人或几个部门？每次能省多少时间？
    ask_l2: 参考句式：「影响__人/__个部门，每次节省约__分钟；不做会__」。
follow_up_order: [techSubtype, businessScenario, acceptanceCriteria, valueImpact]
max_attempts: 2
vague_words: [尽快, 好用, 方便, 优化一下, 越快越好, 体验, 满意, 顺便]
skip_phrases: [不知道, 跳过, 后续补充, 再说吧, 以后再说, 不清楚, 先这样]
optional_fields:                   # 非阻塞：顺带抽取、表单可填、不追问、不判质
  - {key: relatedSystem, label: 关联系统, path: ext.relatedSystem, kind: enum, options: {代销系统: 代销系统, 直销系统: 直销系统, 估值系统: 估值系统, CRM: CRM, 数据中心: 数据中心, 其他: 其他}}
  - {key: relatedModule, label: 关联模块, path: ext.relatedModule, kind: text}
subtype_fields:                    # 按子类展开的补充字段（非阻塞），来自 report/index.vue
  SYS_DEV:
    - {key: devFeatures, label: 涉及功能/流程, placeholder: 如：代销看板-机构持仓页签，涉及查询与导出流程}
    - {key: devPermission, label: 角色与权限, placeholder: 如：机构业务部全员可查，仅主管可导出}
    - {key: devQuality, label: 性能/安全, placeholder: 如：查询3秒内返回；客户敏感信息需脱敏}
  DATA_RPT:
    - {key: dataDimensions, label: 维度与口径, placeholder: 如：按机构汇总前一交易日持仓，与核心系统口径一致}
    - {key: dataSource, label: 数据来源, placeholder: 如：代销系统交易库 + 核心系统持仓}
    - {key: refreshFrequency, label: 刷新频率, placeholder: 如：每个交易日早8:00前刷新}
    - {key: exportRequirement, label: 导出要求, placeholder: 如：支持导出Excel，字段与页面一致}
  SYS_INT:
    - {key: intTargetSystem, label: 对接系统, placeholder: 如：与CRM双向对接}
    - {key: intDataFlow, label: 流向与触发, placeholder: 如：客户风险等级由CRM实时推送}
    - {key: intTimeliness, label: 时效要求, placeholder: 如：数据延迟不超过5分钟}
    - {key: intException, label: 异常处理, placeholder: 如：同步失败自动重试并通知运维}
  OPS_OPT:
    - {key: opsProblem, label: 问题现象, placeholder: 如：月末批量导出Excel等待约10分钟，经常超时}
    - {key: opsScope, label: 影响范围, placeholder: 如：全渠道客户经理，每月初集中使用}
    - {key: opsTarget, label: 期望目标, placeholder: 如：导出1分钟内完成}
common_fields:                     # 所有类型共有的顶层字段（表单渲染用）
  - {key: urgency, label: 紧急程度, kind: enum, options: {NORMAL: 普通, URGENT: 紧急, CRITICAL: 特急}, default: NORMAL}
  - {key: expectDeliveryAt, label: 期望交付时间, kind: date}
```

`matl.yaml` / `train.yaml`：`elements` 仅 title / demandTypeCode / content（required），`follow_up_order` 为空；`optional_fields` 取自 `report/index.vue` 的物料段（materialSubtype、usageScenario、quantity(number)、expectedArrivalAt(date)）和培训段（trainingSubtype、traineeObject、traineeCount(number)、expectedCompleteAt(date)）。

`GET /standards/{type}` 直接返回 YAML 解析后的 JSON（camelCase 键），另附 `contentHash`。

### 2.9 SSO 契约（与 `contract_mock.py` 一致）

- 请求：`POST {base_url}/openapi/demandhub/sso/verify`，body `{"ticket":"..."}`（紧凑 JSON，无空格，签名用同一字符串）
- 头：`X-App-Key`、`X-Timestamp`（毫秒）、`X-Nonce`（uuid4 去横线）、`X-Sign` = `hmac_sha256_hex(app_secret, "POST\n/openapi/demandhub/sso/verify\n{appKey}\n{timestamp}\n{nonce}\n{body}")`
- 超时：`CHANNEL_LS_TIMEOUT_MS`（默认 3000），不重试
- 响应 `errcode` 映射：`0` 成功；`40001/40002/40005` → 1107（文案"登录已失效，请从创金零售重新进入"）；`40003` → 1102（error 日志，文案"登录服务暂时不可用，请稍后重试"）；`40004` → 1113；其他 / 非 200 / 非 JSON / 超时 → 1102
- 熔断：传输层失败（超时、非 200、非 JSON）连续 3 次 → 开启 30s，期间直接抛 1102 不发请求；成功清零
- `user` 字段：`user_id`、`name` 必填（缺失 → 1102 + error 日志），`phone`、`dept_id`、`dept_name`、`dept_path`、`employee_no`、`email` 选填
- 日志脱敏：`mask_ticket`（保留前 4 位 + `***`）、`mask_phone`（`138****0000`）

---

## 3. 任务清单

### P1 骨架、数据库和容器

- T1.1：新增 `server/`、pyproject/uv.lock/.python-version、配置示例、README、Dockerfile/.dockerignore；依赖 fastapi、uvicorn、sqlalchemy[asyncio]、asyncmy、pymysql（同步迁移驱动）、alembic、pydantic-settings、pyjwt、httpx、openai、pyyaml、openpyxl；dev pytest、pytest-asyncio、respx、ruff。若直接用 jiter 必须显式声明依赖，V1 不要求半截 JSON 解析。
- T1.2：Settings APP_ENV 默认 prod，prod 禁 dev-login，JWT_SECRET≥32、生产 CHANNEL_LS 三件套必填；URL 解析 mysql://、jdbc:mysql://，用 SQLAlchemy URL 对象防止凭据重复编码。认证信息必须能 round-trip；无用户名/密码/库名拒绝。异步 asyncmy、迁移 pymysql。
- T1.3：统一返回和异常按 §2；实际 router prefix=/demandhub-api，Kong strip_path=false，root_path 不代替 prefix。dev 才开放专属前缀下 OpenAPI。health 执行 SELECT 1，正常 HTTP200、DB失败503。CORS 仅配置的开发源。普通日志不记录票据/token/密钥。
- T1.4：按方案六表迁移，含 `field_sources`、`revision`、创建去重键、可空草稿标题/类型/内容/编号、会话 demand_id 唯一、asked_target、消息 request_id/request_hash/prompt_version_id 及唯一索引、完整 prompt_version.snapshot；最终需求关联标准版本/内容哈希。服务层避免 demand.session_id 与 session.demand_id 不一致。
- T1.5：新 `deploy/docker-compose.dev.yml` 独立项目，MySQL8 3308、contract-mock 8099，独立卷/测试库。Mock 复制到 server/tests/contract_mock.py，专用 Dockerfile 直接构建此复制，禁止引用以后要删除的旧部署目录。
- T1.6：Python3.12、锁定 uv；构建 `uv sync --frozen --no-dev --no-install-project`；运行直接 `.venv/bin/alembic upgrade head && exec .venv/bin/uvicorn ...`，不能启动时 uv run 安装 dev 依赖。非 root 用户；单业务进程；先以单副本运行迁移，扩副本前单独迁移作业。代理信任范围可配置。
- T1.7：实际构建镜像和 H5 包，测试本地容器与实际路由；平台上传/部署需具备目标环境和真实配置后执行，并保留记录，不能用本地成功替代平台验收。

验收：uv 同步及 MySQL8 upgrade/downgrade/upgrade；配置正反例、公开路径和 DB健康失败测试；镜像无开发依赖，启动不联网安装。隔离测试数据库，不能对用户数据库 downgrade。

### P2 登录与身份

- T2.1–T2.3：逐段移植 §2.9 SSO 签名、签名原始 body、返回映射、超时不重试、失败熔断；严格契约 Mock 验签。ticket一次性，避免自动重试消费。
- T2.4：wecom_userid 唯一 upsert；DISABLED 不能因 SSO 更新变 ACTIVE；并发首次登录不重复建号。资料更新只接收 verify 可信字段。
- T2.5：GET /auth/channel-sso，POST /auth/dev-login（仅开关允许时注册），GET /auth/me。`UserInfo{id,userId,name,deptName,deptPath,channel,isAdmin}`，其中 userId 为企业账号标识；登录返回 accessToken/tokenType/expiresIn/user（前后端保持同一契约）。JWT8h，不做 refresh；每请求查用户 ACTIVE，管理员按当前数据库账号与白名单决定。

验收：签名与 Java/Mock 一致；SSO原有错误映射用例；过期、禁用、非管理员、生产 dev-login 禁止；不会在响应或日志泄露上游原文和密钥。

### P3 标准、草稿和正式记录

- T3.1：三个标准 YAML + loader/schema，标准 API 属性 camelCase（如 optionalFields/subtypeFields/commonFields/followUpOrder），value 的字段路径保持定义；前端不能读取 snake_case 配置键。标准启动时检查重复 key、合法 path、follow_up_order 引用、enum options、所有 kind、rule一致性。子类字段补全 path=ext.key/kind=text。
- T3.2：rules.assess 生成完整要素集，检查空值、枚举、min_len/max_len、any_of/regex、vague_words；语义启发式不能被宣称等同模型理解。硬 schema 校验和软质量状态分开，required 缺失阻止提交，非必填质量缺口允许正式记录。
- T3.3：GET /standards、GET /standards/{type} 登录可读；快照含完整标准、模板原文及 rendererVersion，hash稳定去重；历史需求详情/导出使用关联快照，不读取最新标准来解释旧记录。
- T3.4：编号事务内使用 MySQL锁/原子序列，格式 TYPE-YYYYMMDD-NNN，不在草稿创建时生成。测试独立连接并发新增20条与同一草稿并发提交，不能只测数字唯一。
- T3.5：create_draft/update_draft/submit/close/list_my/get/admin_list。草稿未知类型合法，类型确定后清理不属于该类型的 ext/sources；所有保存入口共用字段白名单、类型、长度、日期、枚举检查，防止客户端mass assignment。唯一 clientRequestId 并发创建也只能一条；请求指纹能判定是否同内容（可增加必要 hash 列）。
- T3.6：submit 在一个短事务 select for update：所有权→已提交则幂等返回→状态/revision→必填及格式→规则复判→保存标准/内容/身份快照→分配编号→状态 SUBMITTED→关联会话关闭→commit。冲突409；提交不调用模型。close仅本人SUBMITTED→CLOSED。管理员可读全量，不能借管理权限改他人的草稿。
- T3.7：列表 `{records,total,size,current,pages}`；详情 `{demand,quality,standard,messages}`，standard是历史快照；草稿尚未提交可用当前标准。路由固定路径 `/my`、admin `/list` 不被 `{id}` 捕获。

验收：不经 Agent 的不完整草稿→补全→提交→查询→撤销；创建/提交并发与幂等；旧revision不覆盖；跨用户读写拒绝；未知/ext类型错误、日期、数字、枚举；提交回滚不消耗编号或留下半条会话状态；标准变更不影响历史导出。

### P4 Agent 抽取、引导和保存

- T4.1：模型输出与请求/最终结果 DTO按§2.6–2.7。JSON围栏容错可保留，非法完整输出不能标成功；缺 key由规则补全，未知/重复 key拒绝。所有模型文本当作数据。
- T4.2：ArkClient使用配置 endpoint、stream=True/json_object；禁用 SDK 隐式多次重试或明确总重试预算。thinking扩展仅配置时传；只有明确不支持thinking的400才去参数重试一次，其他400不冒充兼容问题。连接、读流、格式错误均纳入失败计数；≥3进入60秒冷却；完整输出校验通过才清零。上游流资源在异常和取消时关闭。对外文案1401不泄露原始上游报文。
- T4.3：policy纯函数负责来源保护、完整要素集合、prev askedTarget、attempts与SKIP、选目标、模板问题、三个完成标记。对实际被问目标的未到位回答计次，到2停止；明确跳过只针对该目标。字段值变化重新判质并解除过期SKIP；没有变化不重置次数。required缺口先提示，其他按followUpOrder。默认TECH标default，允许模型改为MATL/TRAIN；明确用户选的类型/字段标user并保护。
- T4.4：prompt从Java底稿改造为抽取/判质助手，标准提供完整key/path/kind/options及当前类型字段；unknown类型提供共用必填与类型列表。输入完整草稿/来源、历史20条、已问目标；不指令模型预先问下一要素。紧急度统一NORMAL/URGENT/CRITICAL，无旧`${...}`占位。
- T4.5：session_service按本人DRAFT创建/读取唯一会话；提交时关闭。list/messages校验所有权。聊天必须检查session.demand_id=req.demandId及owner，不存在“最近ACTIVE会话自动接管”。消息保存本轮requestId/hash、使用的prompt_version_id和最终响应，structuredPayload对外可继续序列化JSON字符串供回放。
- T4.6：guide按方案§6.3：前置校验→去重恢复→会话并发门闩→加载最新草稿与prev askedTarget→渲染版本→LLM流式抽取→完整校验（最多一次修复）→合并/重判/计次→代码选择并生成问题→短事务重检revision/状态/所有权→原子保存草稿和两条消息/askedTarget/响应→commit→成功SSE。禁止模型等待期间持数据库行锁，禁止finally落成功记录。非流式端点调用同一逻辑返回最终结果。
- T4.7：流内error后关闭、不发done；前置失败JSON；取消释放锁/连接。提交与AI竞态、手改与AI竞态只能一方成功，失败方报409并保留可恢复输入。已保存请求的重放不受当前草稿revision变化影响，但返回的是该请求保存的结果；客户端若本地已有更新revision不能用旧重放覆盖。
- T4.8：评测20条多轮，真实模型只评抽取/判质≥80%，代码目标/来源/次数另用确定性测试。pytest默认排除eval，显式 `uv run pytest -m eval -o addopts='' tests/eval` 且需真实Key。报告每条差异及首个可用答复、整轮P50/P95，不能用processing事件计算首字达标。P95可用答复>5s/整轮>20s记录风险与实际endpoint，不擅自改已定模型。

必要验收场景：默认TECH改判物料；用户手改/清空保护；第一问与askedTarget一致；上轮问题回答到位后才选下一题；跳过和到2停止但qualityComplete为false；SKIP字段后来补齐；模型遗漏/重复/未知元素；两个草稿隔离；同请求重放；同ID不同输入冲突；并发手填/提交；DB失败无成功done；断线及恢复；格式连续失败触发冷却。SSE完成必须能立即查询到消息和草稿。

### P5 H5 与整理导出

- T5.1：删除通知、分派、验收、目录和UserPicker等不在V1的H5页面/依赖；保留auth/report/mine/detail及新增admin整理页。开发期间不碰Java/PC/旧部署。
- T5.2：vite base='./'、createWebHashHistory、生产VITE_API_BASE=/demandhub-api。启动守卫在路由前从 location.search 读取外层from/ticket/state，兼容hash query；成功后用history.replaceState同时清除两处一次性参数，保留路由。401清token并给“从创金零售重新进入”，避免无限reload。dev-login界面只在开发构建可见，生产不展示。
- T5.3：API同步§2.6、移除refresh；Bearer统一注入JSON与SSE、下载。Markdown/XLSX使用authenticated fetch→Blob→下载，不能window.open裸URL。处理非文件错误JSON，释放临时Blob URL。
- T5.4：report由standards动态渲染text/enum/number/date，DATE只提交YYYY-MM-DD；来源按路径追踪。保留保存草稿按钮；首次保存或启用Agent先createDraft（稳定clientRequestId防双击），拿到id后URL写draftId；从mine或刷新进入恢复完整草稿/revision/source/会话。无需为了AI先填完title/type/content。
- T5.5：AgentGuideSheet由父页传入demandId/sessionId/revision；不存在会话则按草稿create-or-get，不能捞最近会话。发送前保存手填并获得最新revision，流处理中防止表单与结果互相覆盖；成功只应用服务端已保存的完整结构与sources。元素label从标准来。ready显示按canSubmit，质量缺口单独显示，不能用“已完善”替代“可提交”。识别processing/error/done/EOF/取消，重试复用requestId；新输入新ID；恢复回放和清单。
- T5.6：mine 全部/草稿/已提交/已撤销；detail展示编号、内容、标准字段、质量和对话回放；草稿继续编辑、已提交可撤销。提交前先保存再submit(expectedRevision)，防重复，成功跳detail。草稿标题为空显示合理占位。
- T5.7：新增管理员整理页：按类型/状态/日期筛选全量列表、详情、XLSX导出；入口基于isAdmin，后端独立白名单鉴权。前端路由隐藏不是权限控制。
- T5.8：后端Markdown包含完整字段、质量及会话；XLSX按类型sheet，基本字段/要素状态/optional/subtype列齐全，用户值作为文本避免Excel公式；历史使用快照，草稿无编号用id命名。导出过滤与列表一致；日期上限包含当天。
- T5.9：`npm run build`与`vue-tsc --noEmit`；使用h5-package-build打包并校验禁打包文件/资源/路由/API路径。实际浏览器验证外层ticket+hash路径，保存草稿重进、两草稿会话、异常流恢复、普通人与管理员菜单、带Bearer导出。

### P6 联调与交付

- T6.1：新增 `scripts/e2e_mvp.py`，标准库CLI接受--api-base/--mock-base；Mock签票→真实SSO接口→读取标准→不完整草稿→建对应会话→Agent对话补全→保存确认→提交→mine/detail/回放→Markdown→管理员XLSX→撤销。Agent步骤在提交之前。无真实Key时单独标明mock验证，不能跳过后声称真实模型链路已验收。独立无Agent的API流程也必须通过。
- T6.2：记录本地数据库迁移、后端测试/lint、H5类型检查/构建、浏览器验证、镜像和zip结果。在配置齐备后运行真实endpoint评测与测试平台e2e；创金零售测试入口、Kong路径/流式、iOS/Android真机由真实环境验收。
- T6.3：README列出APP_ENV=prod/AUTH_DEV_LOGIN=false、平台DB/JWT/LLM/SSO注入、白名单、health、生产dev-login404、H5域名配置、模型延迟、回滚方法。凭据只写变量名，发布记录只写commit/tag/digest/产物路径与结果。
- 先完成可审查实现和本地验收。外部发布执行按用户授权及平台技能处理；如果缺少环境或凭据，明确“待外部验收”，不能填已通过。

### P7/P8 范围边界

P7 CLI/Skill不在V1。P8删除旧Java/PC/部署/phase脚本只在真正上线且稳定≥3个工作日后执行；本轮代码完成不能触发提前删除。清理依赖已复制并独立可运行；不自动跑旧phase脚本。

## 4. 协作与提交

所有实现Subagent使用gpt-6.1-sol、reasoning_effort=high，记录实际配置。当前共享分支 `codex/python-mvp`，不切换分支、不合main、不push。主Agent维护两份方案文档、审计及最终验收；后端基础/需求、Agent规则、H5各有单一文件负责人，接口先对齐。修复同样交给指定模型Subagent。阶段报告需列实际命令与结果及未验证项。

## 5. 完成定义

代码交付与上线完成分开记录。代码交付要求：MySQL8迁移/事务并发测试通过，默认pytest与ruff通过，H5类型检查/构建通过，浏览器关键流程与本地E2E通过，镜像与zip可运行，主Agent审计问题已修复。

上线完成额外要求：真实模型评测≥80%并有延迟报告；平台镜像/zip部署验证；测试环境E2E、创金零售SSO及iOS/Android真机链路通过。缺失项必须明确，不能以mock代替。P8为上线后独立工作，不是本次代码实现的前置。

## 6. 版本记录

- v1.1（2026-09-30）：应用用户批准的评审建议，统一草稿/来源/版本/幂等/会话/追问/SSE契约，补管理员页面、hash入口、认证下载、并发及故障验收；明确代码交付与外部上线验收边界。
- v1.0（2026-09-30）：初始实施计划。
