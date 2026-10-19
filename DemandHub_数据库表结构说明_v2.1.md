# DemandHub 数据库表结构说明 v2.1（Python 栈现状）

> 依据：
>
> `server/app/db/models.py`
>
> （SQLAlchemy 2.0 ORM 模型）+ 
>
> `server/alembic/versions/0001~0015`
>
>  迁移脚本逐表核对。
> 数据库：MySQL 8.x，引擎 InnoDB，字符集 
>
> `utf8mb4 / utf8mb4_0900_ai_ci`
>
> ；ORM 驱动 
>
> `mysql+asyncmy`
>
> 。
> 生成时间：2026-10-19。
>
> v2.0 → v2.1 变更（对应 0011~0015 五个迁移）：新增渠道白名单两张表（0011）、`dh_user.role` 默认值改 `REPORTER`（0012）、`dh_user.type_scope` 需求类型权限列（0013）、OneID 一期渠道身份两张表与存量回填（0014）、`dh_user.phone` 全表唯一可作登录账号（0015）；同时**企微管理员白名单（config.admin_wecom_userids 过渡机制）已退役**，管理员判定收敛为 `role='ADMIN'` 唯一口径。
>
> **本文档与代码一一对应，如后续新增迁移须同步更新。**



***

## 1. 系统与代码现状概述

DemandHub（创金合信基金零售业务线需求管理系统）当前主线为 **Python 单体**（FastAPI + SQLAlchemy 2.0 async + Alembic + MySQL），旧 Java 微服务已冻结仅作蓝本。



| 层        | 位置                                                     | 技术栈 / 说明                                         |
| -------- | ------------------------------------------------------ | ------------------------------------------------ |
| 后端 API   | `server/app/api/`                                      | FastAPI，统一前缀 `/demandhub-api`，27 个路由模块           |
| 业务服务     | `server/app/services/`                                 | 需求、流转、通知、SLA、统计、报表、Agent、RAG、授权、身份（OneID）等         |
| 状态机内核    | `server/app/core/statemachine/engine.py`               | 规则落库 + 热重载 + 行锁串行化，每次流转必写日志                      |
| 数据模型     | `server/app/db/models.py`                              | 全部 36 张表的 ORM 定义（唯一权威来源）                         |
| 建表迁移     | `server/alembic/versions/0001~0015`                    | 15 个版本，含种子数据（组织 / 类型 / 渠道 / 字典 / 模板 / SLA / 状态机） |
| AI Agent | `server/app/agent/`                                    | 提报启发、处理辅助、RAG 相似检索，火山方舟大模型                       |
| 标准配置     | `server/app/standards/*.yaml`                          | 科技 / 物料 / 培训三类需求五区字段标准（快照落库）                     |
| H5 移动端   | `frontend/h5/`                                         | Vue 3 + Vant 4，hash 路由，dev 端口 5174               |
| 管理后台     | `frontend/admin/`（构建产物亦在 `server/frontend/admin/dist`） | Vue 3 + Vite，随后端容器同域托管 `/demandhub-api/admin`    |
| 外部对接     | `server/app/sso/chuangjin_ls.py`                       | 创金零售小程序票据 SSO 登录与部门映射                            |

### 1.1 业务主线与状态机

需求主状态 11 个（`demand.status`）：`DRAFT 草稿 → SUBMITTED 待受理 →（NEED_INFO 待补充 / TRIAGE 待分派）→ ANALYZING 分析中 → SOLUTION_REVIEW 方案待评审 → CONFIRMED 已确认/已排期 → IN_PROGRESS 处理中 → ACCEPTANCE 待验收 → DONE 已完成`；任意阶段可 `CLOSED 已关闭`。`ON_HOLD 挂起` 是**叠加态**（不改主状态，由 `hold_snapshot_status` 非空表达）。

角色 5 个：`ADMIN`（超级管理员，状态机全线直通；**唯一管理员判定口径**，config 企微管理员白名单过渡机制已于 0014 时代退役）、`EXECUTIVE`（业务主管，类型修正）、`MANAGER`（承接组织经理，受理 / 分派 / 评审）、`HANDLER`（处理人）、`REPORTER`（提报人，**新建用户默认角色**，0012 起生效，仅可提报与查看自己的需求）；有效角色 = `dh_user.role` 静态角色 ∪ `demand_role_grant` 生效授权（REPORTER 不受 `type_scope` 限制）。

**OneID 身份体系（一期，0014）**：渠道身份独立成表 `dh_channel_identity`（UNIQUE(channel, channel_user_id)，一把渠道钥匙只属于一个人）；渠道用户首次进门照旧自动建档为临时人，管理员在「渠道身份管理」页把未归属身份挂接到 PC 用户（`channel='ACCOUNT'`）名下即完成归并，全程写 `dh_identity_link_log` 审计；不做手机号自动撮合与用户自助绑定；`dh_user.wecom_userid` 一期保留只读对照，登录链路不再读取。`dh_user.phone` 全表唯一（0015），手机号可作为 PC 端登录账号。

### 1.2 全局建模约定



* 主键：`id BIGINT UNSIGNED?`（实际为 `BIGINT AUTO_INCREMENT`，有符号），除 `demand_no_seq` 复合主键外统一。

* 时间：`DATETIME(3)`（毫秒精度），默认 `CURRENT_TIMESTAMP(3)`；多数表有 `created_at`/`updated_at`（ORM `Timestamps` mixin）。应用层时间取 `Asia/Shanghai`。

* 布尔：`TINYINT(1)`，默认 0/1。

* 大文本 / JSON：迁移 DDL 中 `agent_draft.content`、`rag_vector.content/embedding`、`state_machine_config.config_json` 为 `MEDIUMTEXT`，其余文本为 `TEXT`，JSON 字段为 MySQL `JSON`。

* 软删：`demand_attachment.status=DELETED`、`demand_role_grant.is_deleted=行id`（回收不删行）；字典 / 类型 / 渠道 / 组织用 `status=ACTIVE/INACTIVE` 启停。

* 快照冗余：需求表冗余提报人姓名 / 部门、`rag_vector` 冗余编号 / 标题 / 类型，避免历史随主数据变化。

* “只建不用” 预留：`demand.assignee_org_id/submitter_org_id`、`demand_role_grant.org_id/demand_type_scope`、`demand_type.parent_type_code/sla_config`、`demand_channel.config_json` 等一期不参与业务过滤。

* 无外键约束的软关联（代码保证一致性）见第 5 节。



***

## 2. 表总览（36 张，按 5 个业务域分组）



| #  | 表名                          | 中文名称                    | 引入版本                       | 所属域      |
| -- | --------------------------- | ----------------------- | -------------------------- | -------- |
| 1  | `dh_user`                   | 用户（渠道回源 + 账密账号，OneID 归并） | 0001/0005/0012/0013/0015   | 用户与权限    |
| 2  | `refresh_token`             | 刷新令牌（旋转吊销）              | 0005                       | 用户与权限    |
| 3  | `demand_role_grant`         | 业务角色本地授权                | 0008                       | 用户与权限    |
| 4  | `dh_channel_identity`       | 渠道身份（OneID：渠道钥匙→人）      | 0014                       | 用户与权限    |
| 5  | `dh_identity_link_log`     | OneID 挂接 / 改挂审计         | 0014                       | 用户与权限    |
| 6  | `demand_channel_whitelist`  | 渠道白名单（允许谁进）             | 0011                       | 用户与权限    |
| 7  | `demand_channel_whitelist_log` | 渠道白名单操作留痕            | 0011                       | 用户与权限    |
| 8  | `demand`                    | 需求（草稿与正式需求）             | 0001/0002/0006/0008        | 需求核心     |
| 9  | `demand_no_seq`             | 需求编号按日流水                | 0001                       | 需求核心     |
| 10 | `demand_change_log`         | 需求要素变更留痕                | 0002                       | 需求核心     |
| 11 | `demand_attachment`         | 需求附件（图片 / 文档）           | 0004/0006                  | 需求核心     |
| 12 | `demand_relation`           | 需求关系（父子 / 依赖 / 重复 / 拆分） | 0006                       | 需求核心     |
| 13 | `demand_type`               | 需求类型注册                  | 0010                       | 需求核心     |
| 14 | `demand_channel`            | 来源渠道注册（含白名单开关）          | 0010/0011                  | 需求核心     |
| 15 | `demand_org`                | 组织树（物化路径）               | 0010                       | 需求核心     |
| 16 | `channel_dept_unmapped`     | 渠道部门未映射校准清单             | 0010                       | 需求核心     |
| 17 | `sys_dict`                  | 业务字典                    | 0010                       | 需求核心     |
| 18 | `state_machine_config`      | 状态机规则配置（热重载）            | 0006                       | 流转协作     |
| 19 | `demand_transition_log`     | 状态流转日志                  | 0006                       | 流转协作     |
| 20 | `assignment`                | 分派 / 领取 / 退单记录          | 0006                       | 流转协作     |
| 21 | `solution`                  | 需求方案（版本化）               | 0006                       | 流转协作     |
| 22 | `review`                    | 方案 / 验收评审记录             | 0006                       | 流转协作     |
| 23 | `comment`                   | 需求评论                    | 0006                       | 流转协作     |
| 24 | `effort_log`                | 工时记录                    | 0006                       | 流转协作     |
| 25 | `sla_config`                | SLA 停留时长配置              | 0008                       | 流转协作     |
| 26 | `prompt_version`            | 标准与提示词不可变快照             | 0001                       | AI Agent |
| 27 | `agent_session`             | Agent 会话                | 0001/0007                  | AI Agent |
| 28 | `agent_message`             | Agent 消息与幂等响应           | 0001                       | AI Agent |
| 29 | `agent_draft`               | 处理辅助草稿区                 | 0007                       | AI Agent |
| 30 | `rag_vector`                | RAG 需求向量知识库             | 0007                       | AI Agent |
| 31 | `notification`              | 站内信信箱                   | 0008                       | 通知统计     |
| 32 | `notification_template`     | 通知模板                    | 0008                       | 通知统计     |
| 33 | `notification_preference`   | 用户通知偏好                  | 0008                       | 通知统计     |
| 34 | `notify_dedupe`             | 通知去重（替代 Redis）          | 0008                       | 通知统计     |
| 35 | `demand_stat_daily`         | 需求日统计预聚合                | 0008                       | 通知统计     |
| 36 | `report_export_task`        | 报表导出异步任务                | 0008                       | 通知统计     |



***

## 3. 分域表结构详解

列标记：**PK** 主键・**FK** 外键・**UQ** 唯一约束・**NN** 非空・**IDX** 索引前缀。

### 3.1 用户与权限域

#### 3.1.1 `dh_user` — 用户（渠道回源用户 / 账密账号）

同时承载 SSO 回源用户与账密登录用户；账密用户无企微身份，`wecom_userid` 落占位值 `acct:<login_account>`。OneID 一期（0014）：`channel='ACCOUNT'` 的用户即 OneID 用户，渠道身份归并入口见 `dh_channel_identity`；`wecom_userid` 保留只读对照，登录链路不再读取；手机号可作为登录账号（0015）。



| 列                 | 类型           | 约束                                 | 说明                                   |
| ----------------- | ------------ | ---------------------------------- | ------------------------------------ |
| id                | BIGINT       | PK, AUTO\_INCREMENT                | 主键                                   |
| name              | VARCHAR(64)  | NN                                 | 姓名                                   |
| wecom\_userid     | VARCHAR(64)  | NN, UQ                             | 企微 / 渠道用户 ID；账密用户为 `acct:账号`（一期只读对照） |
| phone             | VARCHAR(32)  | UQ `uk_user_phone`（0015）           | 手机号；全表唯一，可作登录账号；渠道临时人为渠道快照脏数据已置 NULL |
| employee\_no      | VARCHAR(32)  |                                    | 工号                                   |
| email             | VARCHAR(128) |                                    | 邮箱                                   |
| dept\_id          | VARCHAR(32)  |                                    | 渠道侧部门 ID（登录回源快照）                     |
| dept\_name        | VARCHAR(128) |                                    | 部门名快照                                |
| dept\_path        | VARCHAR(512) |                                    | 部门路径快照                                |
| channel           | VARCHAR(32)  | NN, 默认 `CHUANGJIN_LS`              | 来源渠道码（账密种子为 `ACCOUNT`，即 OneID 用户）     |
| status            | VARCHAR(16)  | NN, 默认 `ACTIVE`                    | ACTIVE/INACTIVE                      |
| last\_login\_at   | DATETIME(3)  |                                    | 最近登录时间                               |
| login\_account    | VARCHAR(64)  | UQ                                 | 账密登录账号（SSO 用户为空）                     |
| password\_hash    | VARCHAR(128) |                                    | BCrypt 密码哈希，绝不明文                     |
| must\_change\_pwd | TINYINT(1)   | NN, 默认 0                           | 首登强制改密                               |
| fail\_count       | INT          | NN, 默认 0                           | 连续登录失败次数                             |
| locked\_until     | DATETIME(3)  |                                    | 锁定截止时间，过期自动解锁                        |
| role              | VARCHAR(16)  | NN, 默认 `REPORTER`（0012 由 HANDLER 改） | 静态角色：ADMIN/EXECUTIVE/MANAGER/HANDLER/REPORTER |
| type\_scope       | VARCHAR(64)  |（0013）                              | 需求类型权限：逗号分隔类型码，NULL=无权限；仅业务角色生效，ADMIN/REPORTER 不受限 |
| created\_at       | DATETIME(3)  | NN, 默认 CURRENT\_TIMESTAMP (3)      | 创建时间                                 |
| updated\_at       | DATETIME(3)  | NN, 默认 / 更新 CURRENT\_TIMESTAMP (3) | 更新时间                                 |

索引：`UNIQUE(wecom_userid)`、`UNIQUE(login_account)`（索引名 `uk_dh_user_login_account`）、`UNIQUE(phone)`（索引名 `uk_user_phone`，0015；MySQL 唯一索引允许多个 NULL）。

#### 3.1.2 `refresh_token` — 刷新令牌



| 列           | 类型           | 约束                      | 说明                     |
| ----------- | ------------ | ----------------------- | ---------------------- |
| id          | BIGINT       | PK                      | 主键                     |
| user\_id    | BIGINT       | NN, FK→dh\_user.id, IDX | 所属用户                   |
| token\_hash | VARCHAR(128) | NN, UQ                  | refresh token 哈希（不落原文） |
| expires\_at | DATETIME(3)  | NN                      | 过期时间（默认 7 天，可配 1\~90）  |
| revoked     | TINYINT(1)   | NN, 默认 0                | 是否已吊销（旋转 / 登出 / 改密置 1） |
| created\_at | DATETIME(3)  | NN                      | 签发时间                   |

#### 3.1.3 `demand_role_grant` — 业务角色本地授权

EXECUTIVE/MANAGER 等角色的额外授权；有效期到点自动生效 / 失效；软删时 `is_deleted` 置为行 id。



| 列                         | 类型           | 约束                 | 说明                              |
| ------------------------- | ------------ | ------------------ | ------------------------------- |
| id                        | BIGINT       | PK                 | 主键                              |
| user\_id                  | BIGINT       | NN, FK→dh\_user.id | 被授权人                            |
| role\_code                | VARCHAR(32)  | NN, IDX            | ADMIN/EXECUTIVE/MANAGER/HANDLER |
| org\_id                   | BIGINT       |                    | 授权组织（一期留口，不过滤）                  |
| demand\_type\_scope       | VARCHAR(256) |                    | 类型码逗号多选；NULL = 全部类型（一期不过滤）      |
| effective\_from           | DATETIME(3)  |                    | 生效起（NULL = 立即）                  |
| effective\_to             | DATETIME(3)  |                    | 生效止（NULL = 长期）                  |
| granted\_by               | BIGINT       | FK→dh\_user.id     | 授予人                             |
| is\_deleted               | INT          | NN, 默认 0           | 0 = 生效；回收时置为行 id                |
| created\_at / updated\_at | DATETIME(3)  | NN                 | 时间戳                             |

约束：`UNIQUE(user_id, role_code, org_id, demand_type_scope, is_deleted)` 名 `uk_grant`；`IDX(role_code)`。

#### 3.1.4 `dh_channel_identity` — 渠道身份（OneID 一期核心表）

一行 = 一把渠道钥匙，`UNIQUE(channel, channel_user_id)` 保证只属于一个人。未归并时 `user_id` 指向渠道自动建档的临时人（`dh_user.channel != 'ACCOUNT'`）；管理员挂接后指向 PC 用户（OneID 用户），渠道免登进入的即该 PC 用户。0014 附带存量回填：非 ACCOUNT 用户每人生成一条指向自己的身份记录（`INSERT IGNORE` 幂等）。



| 列                   | 类型          | 约束                          | 说明                             |
| ------------------- | ----------- | --------------------------- | ------------------------------ |
| id                  | BIGINT      | PK                          | 主键                             |
| user\_id            | BIGINT      | NN, FK→dh\_user.id, IDX     | 归属人（临时人或挂接后的 OneID 用户）          |
| channel             | VARCHAR(32) | NN, UQ 组合 `uk_channel_identity` | 渠道码（utf8mb4\_unicode\_ci，随 dh\_user） |
| channel\_user\_id   | VARCHAR(64) | NN, UQ 组合                    | 渠道侧用户编号（企微 userid）              |
| channel\_user\_name | VARCHAR(64) |                             | 渠道侧姓名快照（每次进门更新，供管理员识别）         |
| created\_at         | DATETIME(3) | NN                          | 首次进门时间                         |
| updated\_at         | DATETIME(3) | NN, ON UPDATE 自动刷新          | 最近进门时间                         |

约束：`UNIQUE(channel, channel_user_id)` 名 `uk_channel_identity`；`INDEX(user_id)` 名 `ix_channel_identity_user`。

#### 3.1.5 `dh_identity_link_log` — OneID 挂接 / 改挂审计

行只增不改。`LINK`（挂接）搬数据并记 `moved_counts` 过户明细 JSON；`REBIND`（改挂）不搬数据、`moved_counts` 为 NULL。人员列全部落姓名快照，主数据后续改名不影响历史回溯。



| 列                 | 类型           | 约束            | 说明                            |
| ----------------- | ------------ | ------------- | ----------------------------- |
| id                | BIGINT        | PK            | 主键                            |
| action            | VARCHAR(16)   | NN            | LINK 挂接 / REBIND 改挂           |
| identity\_id      | BIGINT        | NN            | 渠道身份（dh\_channel\_identity.id） |
| channel           | VARCHAR(32)   | NN            | 渠道码快照                         |
| channel\_user\_id | VARCHAR(64)   | NN            | 渠道侧用户编号快照                    |
| from\_user\_id    | BIGINT        | NN            | 原归属人                          |
| from\_user\_name  | VARCHAR(64)   | NN            | 原归属人姓名快照                     |
| to\_user\_id      | BIGINT        | NN            | 新归属人                          |
| to\_user\_name    | VARCHAR(64)   | NN            | 新归属人姓名快照                     |
| moved\_counts     | VARCHAR(512)  |               | 过户数据量明细 JSON（仅 LINK；REBIND 为 NULL） |
| operator\_id      | BIGINT        | NN            | 操作人                           |
| operator\_name    | VARCHAR(64)   | NN            | 操作人姓名快照                      |
| created\_at       | DATETIME(3)   | NN            | 操作时间                          |

约束：`INDEX(identity_id, created_at)` 名 `ix_link_log_identity`。

#### 3.1.6 `demand_channel_whitelist` — 渠道白名单

管「允许谁进」，与 `dh_user` 用户档案相互独立（登录命中才建档）。开关挂在 `demand_channel.whitelist_enabled`（默认关 = 全放行），拦截页联系引导文案走 `demand_channel.whitelist_contact` 随渠道配置（公开接口读取）。



| 列                  | 类型          | 约束                        | 说明                    |
| ------------------ | ----------- | ------------------------- | --------------------- |
| id                 | BIGINT      | PK                        | 主键                    |
| channel\_code      | VARCHAR(32) | NN, UQ 组合 `uk_whitelist_user` | 渠道码                   |
| channel\_user\_id  | VARCHAR(64) | NN, UQ 组合                  | 渠道侧用户编号（企微 userid）    |
| display\_name      | VARCHAR(64) |                           | 展示姓名（便于管理员识别，非身份凭证）  |
| status             | VARCHAR(16) | NN, 默认 `ENABLED`           | ENABLED/DISABLED      |
| created\_by        | BIGINT      |                           | 建档操作人（软关联 dh\_user.id） |
| created\_by\_name  | VARCHAR(64) |                           | 建档操作人姓名快照             |
| created\_at / updated\_at | DATETIME(3) | NN                 | 时间戳                   |

约束：`UNIQUE(channel_code, channel_user_id)` 名 `uk_whitelist_user`。

#### 3.1.7 `demand_channel_whitelist_log` — 渠道白名单操作留痕

白名单增 / 删 / 启停 / 渠道开关与文案变更的操作留痕；操作对象落快照，行只增不改。



| 列                 | 类型           | 约束        | 说明                    |
| ----------------- | ------------ | --------- | --------------------- |
| id                | BIGINT        | PK        | 主键                    |
| action            | VARCHAR(24)   | NN        | 操作类型（增/删/启停/开关/文案）   |
| channel\_code     | VARCHAR(32)   | NN        | 渠道码                   |
| channel\_user\_id | VARCHAR(64)   |           | 渠道侧用户编号（渠道级操作为空）     |
| operator\_id      | BIGINT        | NN        | 操作人                   |
| operator\_name    | VARCHAR(64)   | NN        | 操作人姓名快照               |
| detail            | VARCHAR(512)  |           | 操作详情                  |
| created\_at       | DATETIME(3)   | NN        | 操作时间                  |

约束：`INDEX(channel_code, created_at)` 名 `ix_whitelist_log_channel`。



***

### 3.2 需求核心域

#### 3.2.1 `demand` — 需求（草稿与正式需求，系统核心表）



| 列                         | 类型           | 约束                        | 说明                                           |
| ------------------------- | ------------ | ------------------------- | -------------------------------------------- |
| id                        | BIGINT       | PK                        | 主键                                           |
| demand\_no                | VARCHAR(40)  | UQ                        | 正式编号（提交时由 demand\_no\_seq 发号，草稿为空）           |
| title                     | VARCHAR(256) |                           | 标题                                           |
| demand\_type\_code        | VARCHAR(32)  | IDX 组合                    | 需求类型码：TECH/MATL/TRAIN                        |
| subtype\_code             | VARCHAR(32)  |                           | 子类型码（如 TECH\_SUBTYPE）                        |
| content                   | TEXT         |                           | 需求描述正文                                       |
| urgency                   | VARCHAR(16)  |                           | 紧急程度 NORMAL/URGENT/CRITICAL（0003 起可空，提交前须确认） |
| expect\_delivery\_at      | DATE         |                           | 期望交付日期                                       |
| ext                       | JSON         | NN                        | 扩展区要素（五区表单之外的扩展键值）                           |
| elements                  | JSON         |                           | A/B/C/D 区要素值（标准配置驱动的五区表单）                    |
| quality                   | JSON         |                           | 质量区要素（E 区：验收标准 / 评分等）                        |
| field\_sources            | JSON         | NN                        | 字段来源标记（user/agent/default，用于审计）              |
| revision                  | INT          | NN, 默认 0                  | 乐观锁 / 修订版本号，每次流转 +1                          |
| client\_request\_id       | VARCHAR(64)  | NN                        | 客户端幂等 ID                                     |
| create\_request\_hash     | VARCHAR(64)  | NN                        | 创建请求哈希（幂等防重）                                 |
| standard\_version\_id     | BIGINT       | FK→prompt\_version.id     | 提交时绑定的五区标准快照版本                               |
| quality\_content\_hash    | VARCHAR(64)  |                           | 质量内容哈希（变更检测）                                 |
| status                    | VARCHAR(16)  | NN, 默认 `DRAFT`            | 主状态（11 态，见 1.1）                              |
| submitter\_id             | BIGINT       | NN, FK→dh\_user.id        | 提报人                                          |
| submitter\_name           | VARCHAR(64)  |                           | 提报人姓名快照                                      |
| submitter\_dept           | VARCHAR(128) |                           | 提报人部门快照（看板 Top10 用）                          |
| channel                   | VARCHAR(32)  |                           | 提报渠道码                                        |
| session\_id               | BIGINT       | UQ（软关联 agent\_session.id） | 提报启发会话 ID                                    |
| split\_from\_id           | BIGINT       | FK→demand.id（自引用）         | 拆分来源需求；NULL = 独立需求                           |
| split\_group\_id          | VARCHAR(36)  | IDX                       | 同源拆分批次 UUID                                  |
| submitted\_at             | DATETIME(3)  | IDX                       | 提交时间                                         |
| closed\_at                | DATETIME(3)  |                           | 关闭时间                                         |
| close\_reason             | VARCHAR(256) |                           | 关闭原因（字典 CLOSE\_REASON）                       |
| assignee\_id              | BIGINT       | FK→dh\_user.id            | 当前处理人                                        |
| hold\_snapshot\_status    | VARCHAR(32)  | IDX                       | 挂起前主状态；非空即挂起中（叠加态）                           |
| hold\_reason              | VARCHAR(256) |                           | 挂起原因                                         |
| confirmed\_at             | DATETIME(3)  |                           | 方案评审通过（确认 / 排期）时间                            |
| done\_at                  | DATETIME(3)  |                           | 验收通过时间                                       |
| quality\_score            | SMALLINT     |                           | 验收质量评分 1-5                                   |
| satisfaction\_score       | SMALLINT     |                           | 验收满意度评分 1-5                                  |
| assignee\_org\_id         | BIGINT       |                           | 承接组织（一期只建不用，软关联 demand\_org）                 |
| submitter\_org\_id        | BIGINT       |                           | 提报组织（一期只建不用）                                 |
| created\_at / updated\_at | DATETIME(3)  | NN                        | 时间戳                                          |

约束与索引：



* `UNIQUE(submitter_id, client_request_id)` 名 `uq_demand_create`（创建幂等）；

* `UNIQUE(demand_no)`、`UNIQUE(session_id)`；

* `ix_demand_owner_status(submitter_id, status)`、`ix_demand_type_status(demand_type_code, status)`、`ix_demand_submitted(submitted_at)`、`ix_demand_split_group(split_group_id)`、`ix_demand_split_from(split_from_id)`、`ix_demand_assignee_status(assignee_id, status)`、`ix_demand_hold_snapshot(hold_snapshot_status)`；

* 外键：`submitter_id`、`assignee_id`、`standard_version_id`、`split_from_id`（自引用）。

#### 3.2.2 `demand_no_seq` — 编号按日流水

复合主键，发号格式 `类型码-YYYYMMDD-当日序号`（如 `TECH-20261016-001`）。



| 列          | 类型          | 约束       | 说明     |
| ---------- | ----------- | -------- | ------ |
| biz\_date  | DATE        | PK       | 业务日期   |
| type\_code | VARCHAR(32) | PK       | 需求类型码  |
| seq        | INT         | NN, 默认 0 | 当日已发序号 |

#### 3.2.3 `demand_change_log` — 要素变更留痕（E7 审计）



| 列           | 类型          | 约束               | 说明                                                           |
| ----------- | ----------- | ---------------- | ------------------------------------------------------------ |
| id          | BIGINT      | PK               | 主键                                                           |
| demand\_id  | BIGINT      | NN, FK→demand.id | 需求 ID（IDX 组合 `ix_change_demand_time(demand_id, created_at)`） |
| field\_key  | VARCHAR(64) | NN               | 要素 key：B1/D8/ext.techSubtype/quality.\* 等                    |
| old\_value  | JSON        |                  | 修改前值                                                         |
| new\_value  | JSON        |                  | 修改后值                                                         |
| source      | VARCHAR(16) | NN, 默认 `user`    | user/agent/default                                           |
| changed\_by | BIGINT      | FK→dh\_user.id   | 操作人；Agent 写入为 NULL                                           |
| created\_at | DATETIME(3) | NN               | 留痕时间                                                         |

#### 3.2.4 `demand_attachment` — 需求附件

文件本体在服务端本地目录（`storage/attachments/<demand_id>/`），`storage_key` 不外泄，下载走鉴权接口；仅随需求流转，不做多模态识别。



| 列                         | 类型           | 约束                 | 说明                                                       |
| ------------------------- | ------------ | ------------------ | -------------------------------------------------------- |
| id                        | BIGINT       | PK                 | 主键                                                       |
| demand\_id                | BIGINT       | NN, FK→demand.id   | 需求 / 草稿 ID（IDX `ix_attachment_demand_id(demand_id, id)`） |
| file\_name                | VARCHAR(256) | NN                 | 原始文件名                                                    |
| kind                      | VARCHAR(16)  | NN                 | IMAGE/DOC                                                |
| file\_ext                 | VARCHAR(16)  | NN                 | 扩展名（小写，白名单校验）                                            |
| size                      | INT          | NN                 | 文件大小（字节）                                                 |
| storage\_key              | VARCHAR(128) | NN, UQ             | 存储键（uuid，目录内相对定位）                                        |
| uploaded\_by              | BIGINT       | NN, FK→dh\_user.id | 上传人                                                      |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE`    | ACTIVE/DELETED（软删；提交后不可删）                                |
| biz\_type                 | VARCHAR(16)  | NN, 默认 `DEMAND`    | 归属类型：DRAFT/DEMAND/SOLUTION/COMMENT                       |
| biz\_id                   | BIGINT       |                    | 业务对象 id（SOLUTION/COMMENT 用；DEMAND 时同 demand\_id）         |
| created\_at / updated\_at | DATETIME(3)  | NN                 | 时间戳                                                      |

#### 3.2.5 `demand_relation` — 需求关系



| 列           | 类型          | 约束               | 说明                                               |
| ----------- | ----------- | ---------------- | ------------------------------------------------ |
| id          | BIGINT      | PK               | 主键                                               |
| from\_id    | BIGINT      | NN, FK→demand.id | 源需求                                              |
| to\_id      | BIGINT      | NN, FK→demand.id | 目标需求（IDX `idx_relation_to`）                      |
| type        | VARCHAR(16) | NN               | PARENT 父子 / DEPENDS 依赖 / DUPLICATE 重复 / SPLIT 拆分 |
| created\_at | DATETIME(3) | NN               | 创建时间                                             |

约束：`UNIQUE(from_id, to_id, type)` 名 `uk_relation_pair`。

#### 3.2.6 `demand_type` — 需求类型注册

表管注册 / 启停 / 状态机绑定 / 排序；五区字段标准仍走 `standards/*.yaml` 快照。



| 列                         | 类型          | 约束                    | 说明                                        |
| ------------------------- | ----------- | --------------------- | ----------------------------------------- |
| id                        | BIGINT      | PK                    | 主键                                        |
| type\_code                | VARCHAR(32) | NN, UQ `uk_type_code` | 类型编码（大写）                                  |
| type\_name                | VARCHAR(64) | NN                    | 类型名称（科技 / 物料 / 培训）                        |
| parent\_type\_code        | VARCHAR(32) |                       | 父类型（预留，一期不用）                              |
| default\_org\_id          | BIGINT      |                       | 默认承接组织（软关联 demand\_org.id；种子 111/121/131） |
| state\_machine\_key       | VARCHAR(64) | NN, 默认 `DEFAULT`      | 绑定状态机配置 key                               |
| sla\_config               | JSON        |                       | 类型级 SLA（预留，一期走 sla\_config 表）             |
| sort                      | INT         | NN, 默认 0              | 排序                                        |
| status                    | VARCHAR(16) | NN, 默认 `ACTIVE`       | ACTIVE/INACTIVE                           |
| created\_at / updated\_at | DATETIME(3) | NN                    | 时间戳                                       |

种子：TECH 科技需求（默认组织 111 科技产品一组）、MATL 物料需求（121 客户陪伴一组）、TRAIN 培训需求（131 培训开发一组）。

#### 3.2.7 `demand_channel` — 来源渠道注册

只做登记 / 启停；SSO 对接参数走 `.env` 不迁表。



| 列                         | 类型          | 约束                       | 说明              |
| ------------------------- | ----------- | ------------------------ | --------------- |
| id                        | BIGINT      | PK                       | 主键              |
| channel\_code             | VARCHAR(32) | NN, UQ `uk_channel_code` | 渠道码             |
| channel\_name             | VARCHAR(64) | NN                       | 渠道名称            |
| app\_id                   | VARCHAR(64) |                          | 渠道侧应用 ID        |
| callback\_enabled         | TINYINT(1)  | NN, 默认 0                 | 回调是否启用          |
| status                    | VARCHAR(16) | NN, 默认 `ACTIVE`          | ACTIVE/DISABLED |
| whitelist\_enabled        | TINYINT(1)  | NN, 默认 0（0011）           | 渠道白名单开关（默认关=全放行） |
| whitelist\_contact        | VARCHAR(255) |（0011）                   | 非白名单拦截页联系引导文案 |
| config\_json              | JSON        |                          | 渠道配置（预留）        |
| created\_at / updated\_at | DATETIME(3) | NN                       | 时间戳             |

种子：`WEB` PC 管理端、`CHUANGJIN_LS` 创金零售小程序（ACTIVE）；`WECOM_APP/WECOM_BOT/FEISHU_BOT/DOUBAO_WORK/WORKBUDDY/VOICE` 预留 DISABLED。

#### 3.2.8 `demand_org` — 组织树（物化路径）

路径格式 `/100/110/`（尾斜杠），子树用 `startsWith` 前缀匹配；`external_dept_id` 用于票据登录部门映射，未命中挂虚拟组织 900。



| 列                         | 类型           | 约束                 | 说明                                 |
| ------------------------- | ------------ | ------------------ | ---------------------------------- |
| id                        | BIGINT       | PK                 | 主键（种子保留 100\~141、900）              |
| name                      | VARCHAR(128) | NN                 | 组织名称                               |
| level                     | VARCHAR(16)  | NN                 | LINE 业务线 / DEPT 部门 / GROUP 小组      |
| parent\_id                | BIGINT       | NN, 默认 0           | 父组织（0 = 根；无 DB 外键，自关联）             |
| path                      | VARCHAR(512) | NN, IDX `idx_path` | 物化路径                               |
| org\_kind                 | VARCHAR(16)  |                    | REPORTER 提报侧 / ASSIGNER 承接侧 / BOTH |
| external\_flag            | TINYINT(1)   | NN, 默认 0           | 是否外部虚拟组织（900=1）                    |
| external\_dept\_id        | VARCHAR(32)  |                    | 渠道侧部门 ID（登录映射用）                    |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE`    | ACTIVE/INACTIVE                    |
| created\_at / updated\_at | DATETIME(3)  | NN                 | 时间戳                                |

索引：`idx_parent(parent_id)`、`idx_path(path)`、`idx_status(status)`。

种子：100 创金合信零售业务线 → 110 财管科技产品部（111/112 组）、120 客户陪伴服务部（121 组）、130 培训开发部（131 组）、140 零售一线营业部（141 组）；900 外部 / 待确认（虚拟根）。

#### 3.2.9 `channel_dept_unmapped` — 渠道部门未映射校准清单

登录部门映射未命中时 upsert 计数，管理员校准后删行。



| 列                         | 类型           | 约束        | 说明                   |
| ------------------------- | ------------ | --------- | -------------------- |
| id                        | BIGINT       | PK        | 主键                   |
| channel\_code             | VARCHAR(32)  | NN, UQ 组合 | 渠道码                  |
| dept\_id                  | VARCHAR(32)  | NN, UQ 组合 | 渠道侧部门 ID             |
| dept\_name                | VARCHAR(128) |           | 部门名                  |
| dept\_path                | VARCHAR(256) |           | 部门路径                 |
| sample\_channel\_user\_id | VARCHAR(64)  |           | 最近命中的渠道用户 ID（排查样本）   |
| hit\_count                | INT          | NN, 默认 1  | 未映射命中次数              |
| first\_seen\_at           | DATETIME(3)  | NN        | 首次命中                 |
| last\_seen\_at            | DATETIME(3)  | NN        | 最近命中（ON UPDATE 自动刷新） |

约束：`UNIQUE(channel_code, dept_id)` 名 `uk_channel_dept`。

#### 3.2.10 `sys_dict` — 业务字典

编码不可改，仅名称 / 排序 / 状态可编辑。



| 列                         | 类型           | 约束              | 说明              |
| ------------------------- | ------------ | --------------- | --------------- |
| id                        | BIGINT       | PK              | 主键              |
| dict\_type                | VARCHAR(64)  | NN, UQ 组合       | 字典分组            |
| item\_code                | VARCHAR(64)  | NN, UQ 组合       | 项编码             |
| item\_name                | VARCHAR(128) | NN              | 项名称             |
| sort                      | INT          | NN, 默认 0        | 排序              |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE` | ACTIVE/INACTIVE |
| created\_at / updated\_at | DATETIME(3)  | NN              | 时间戳             |

约束：`UNIQUE(dict_type, item_code)` 名 `uk_dict`。

种子（21 项）：URGENCY（3）、CLOSE\_REASON（3）、HOLD\_REASON（3）、TECH\_SUBTYPE（5）、RELATED\_SYSTEM（6；存储值取 item\_name，兼容历史自由文本）。



***

### 3.3 流转与协作域

#### 3.3.1 `state_machine_config` — 状态机规则配置（热重载）



| 列                         | 类型           | 约束                        | 说明                                               |
| ------------------------- | ------------ | ------------------------- | ------------------------------------------------ |
| id                        | BIGINT       | PK                        | 主键                                               |
| config\_key               | VARCHAR(64)  | NN, UQ `uk_sm_config_key` | 配置标识（DEFAULT；可按类型绑定多套）                           |
| config\_name              | VARCHAR(128) | NN                        | 配置名称                                             |
| config\_json              | MEDIUMTEXT   | NN                        | 规则 JSON：`{rules:[{from,event,to,roles,remark}]}` |
| version                   | INT          | NN, 默认 1                  | 版本号，每次更新 +1（热重载判断依据）                             |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE`           | ACTIVE/INACTIVE                                  |
| remark                    | VARCHAR(512) |                           | 备注                                               |
| created\_at / updated\_at | DATETIME(3)  | NN                        | 时间戳                                              |

种子：`DEFAULT` 默认状态机（当前约 32 条规则；角色口径：受理族 = MANAGER，CHANGE\_TYPE=EXECUTIVE，处理族 = HANDLER，可代办族 = HANDLER+MANAGER，ADMIN 引擎直通）。

#### 3.3.2 `demand_transition_log` — 状态流转日志（每次流转必写，只追加）



| 列                  | 类型           | 约束                 | 说明                                                             |
| ------------------ | ------------ | ------------------ | -------------------------------------------------------------- |
| id                 | BIGINT       | PK                 | 主键                                                             |
| demand\_id         | BIGINT       | NN, FK→demand.id   | 需求 ID（IDX `idx_transition_demand_time(demand_id, created_at)`） |
| from\_status       | VARCHAR(32)  |                    | 源状态（SPLIT 建单类可空）                                               |
| to\_status         | VARCHAR(32)  | NN                 | 目标状态（挂起时为 ON\_HOLD）                                            |
| event              | VARCHAR(64)  | NN                 | 事件名（19 种，含 SPLIT）                                              |
| operator\_id       | BIGINT       | NN, FK→dh\_user.id | 操作人                                                            |
| operator\_snapshot | VARCHAR(128) |                    | 操作人姓名快照                                                        |
| hold\_flag         | TINYINT(1)   | NN, 默认 0           | 是否挂起 / 恢复类事件                                                   |
| comment            | TEXT         |                    | 流转备注（退回原因 / 挂起原因等）                                             |
| extra              | JSON         |                    | 扩展信息（如分派目标人、新类型）                                               |
| created\_at        | DATETIME(3)  | NN                 | 发生时间                                                           |

#### 3.3.3 `assignment` — 分派 / 领取 / 退单记录



| 列              | 类型          | 约束                 | 说明                                                             |
| -------------- | ----------- | ------------------ | -------------------------------------------------------------- |
| id             | BIGINT      | PK                 | 主键                                                             |
| demand\_id     | BIGINT      | NN, FK→demand.id   | 需求 ID（IDX `idx_assignment_demand`）                             |
| from\_user\_id | BIGINT      |                    | 原处理人（退回池时用；软关联 dh\_user）                                       |
| to\_user\_id   | BIGINT      |                    | 新处理人（软关联 dh\_user；IDX `idx_assignment_to(to_user_id, action)`） |
| action         | VARCHAR(16) | NN                 | ASSIGN 分派 / CLAIM 领取 / RETURN 退回                               |
| operator\_id   | BIGINT      | NN, FK→dh\_user.id | 操作人                                                            |
| created\_at    | DATETIME(3) | NN                 | 发生时间                                                           |

#### 3.3.4 `solution` — 需求方案（版本化）



| 列                         | 类型           | 约束                 | 说明                                |
| ------------------------- | ------------ | ------------------ | --------------------------------- |
| id                        | BIGINT       | PK                 | 主键                                |
| demand\_id                | BIGINT       | NN, FK→demand.id   | 需求 ID（IDX `idx_solution_demand`）  |
| version                   | INT          | NN                 | 版本号，同需求内递增                        |
| author\_id                | BIGINT       | NN, FK→dh\_user.id | 作者                                |
| spec\_content             | TEXT         |                    | 需求规约                              |
| solution\_content         | TEXT         |                    | 方案内容                              |
| plan\_delivery\_at        | DATE         |                    | 计划交付时间（评审联动）                      |
| status                    | VARCHAR(16)  | NN, 默认 `DRAFT`     | DRAFT/SUBMITTED/APPROVED/REJECTED |
| remark                    | VARCHAR(512) |                    | 备注                                |
| created\_at / updated\_at | DATETIME(3)  | NN                 | 时间戳                               |

约束：`UNIQUE(demand_id, version)` 名 `uk_solution_demand_version`。

#### 3.3.5 `review` — 方案与验收评审记录（留痕不可改）



| 列                   | 类型               | 约束                 | 说明                                                          |
| ------------------- | ---------------- | ------------------ | ----------------------------------------------------------- |
| id                  | BIGINT           | PK                 | 主键                                                          |
| demand\_id          | BIGINT           | NN, FK→demand.id   | 需求 ID（IDX `idx_review_demand_type(demand_id, review_type)`） |
| review\_type        | VARCHAR(16)      | NN                 | SOLUTION 方案评审 / ACCEPTANCE 验收                               |
| target\_id          | BIGINT           | FK→solution.id     | 方案评审时指向被评方案                                                 |
| result              | VARCHAR(16)      | NN                 | PASS/REJECT                                                 |
| opinion             | TEXT             |                    | 评审意见（REJECT 必填）                                             |
| quality\_score      | TINYINT UNSIGNED |                    | 质量评分 1-5（验收 PASS 必填）                                        |
| satisfaction\_score | TINYINT UNSIGNED |                    | 满意度评分 1-5（验收 PASS 必填）                                       |
| reviewer\_id        | BIGINT           | NN, FK→dh\_user.id | 评审人                                                         |
| created\_at         | DATETIME(3)      | NN                 | 评审时间                                                        |

#### 3.3.6 `comment` — 需求评论（仅作者可改，不可删）



| 列                         | 类型           | 约束                 | 说明                                                          |
| ------------------------- | ------------ | ------------------ | ----------------------------------------------------------- |
| id                        | BIGINT       | PK                 | 主键                                                          |
| demand\_id                | BIGINT       | NN, FK→demand.id   | 需求 ID（IDX `idx_comment_demand_time(demand_id, created_at)`） |
| author\_id                | BIGINT       | NN, FK→dh\_user.id | 作者                                                          |
| content                   | TEXT         | NN                 | 评论内容                                                        |
| mentioned\_user\_ids      | VARCHAR(512) |                    | @用户 ID 列表，逗号分隔                                              |
| created\_at / updated\_at | DATETIME(3)  | NN                 | 时间戳                                                         |

#### 3.3.7 `effort_log` — 工时记录



| 列                         | 类型           | 约束                 | 说明                                                  |
| ------------------------- | ------------ | ------------------ | --------------------------------------------------- |
| id                        | BIGINT       | PK                 | 主键                                                  |
| demand\_id                | BIGINT       | NN, FK→demand.id   | 需求 ID（IDX `idx_effort_demand`）                      |
| user\_id                  | BIGINT       | NN, FK→dh\_user.id | 登记人（IDX `idx_effort_user_date(user_id, work_date)`） |
| hours                     | DECIMAL(5,1) | NN, 默认 0           | 工时（0 < h ≤ 24）                                      |
| work\_date                | DATE         | NN                 | 工作日期                                                |
| remark                    | VARCHAR(512) |                    | 备注                                                  |
| created\_at / updated\_at | DATETIME(3)  | NN                 | 时间戳                                                 |

#### 3.3.8 `sla_config` — SLA 停留时长配置（类型 × 状态）



| 列                         | 类型           | 约束        | 说明                                                       |
| ------------------------- | ------------ | --------- | -------------------------------------------------------- |
| id                        | BIGINT       | PK        | 主键                                                       |
| demand\_type\_code        | VARCHAR(32)  | NN, UQ 组合 | 需求类型码                                                    |
| status                    | VARCHAR(32)  | NN, UQ 组合 | 停留状态（SUBMITTED/TRIAGE/ANALYZING/IN\_PROGRESS/ACCEPTANCE） |
| warn\_minutes             | INT          | NN        | 黄色预警阈值（分钟）                                               |
| max\_minutes              | INT          | NN        | 红色告警阈值（分钟）                                               |
| enabled                   | TINYINT(1)   | NN, 默认 1  | 是否启用                                                     |
| remark                    | VARCHAR(512) |           | 备注                                                       |
| created\_at / updated\_at | DATETIME(3)  | NN        | 时间戳                                                      |

约束：`UNIQUE(demand_type_code, status)` 名 `uk_type_status`。种子 11 条（TECH 五态 + MATL 三态 + TRAIN 三态，如 TECH 受理 1 天预警 / 2 天告警、处理 5 天 / 10 天）。后台扫描器默认 30 秒一轮，告警经 `notify_dedupe` 去重后写站内信。



***

### 3.4 AI Agent 域

#### 3.4.1 `prompt_version` — 标准与提示词不可变快照



| 列             | 类型          | 约束     | 说明                           |
| ------------- | ----------- | ------ | ---------------------------- |
| id            | BIGINT      | PK     | 主键                           |
| code          | VARCHAR(64) | NN     | 快照编码（标准 / 提示词标识，如 TECH 五区标准） |
| version       | VARCHAR(32) | NN     | 版本号                          |
| content\_hash | VARCHAR(64) | NN, UQ | 内容哈希（同内容幂等不重复落库）             |
| snapshot      | JSON        | NN     | 快照全文（标准 / 系统提示词）             |
| created\_at   | DATETIME(3) | NN     | 创建时间                         |

#### 3.4.2 `agent_session` — Agent 会话

一个需求可并存两类会话：`SUBMIT_GUIDE` 提报启发（每草稿唯一）、`HANDLE_ASSIST` 处理辅助（每需求唯一）。



| 列                         | 类型           | 约束                    | 说明                           |
| ------------------------- | ------------ | --------------------- | ---------------------------- |
| id                        | BIGINT       | PK                    | 主键                           |
| session\_no               | VARCHAR(64)  | NN, UQ                | 会话业务编号                       |
| user\_id                  | BIGINT       | NN, FK→dh\_user.id    | 发起用户                         |
| scene                     | VARCHAR(32)  | NN, 默认 `SUBMIT_GUIDE` | SUBMIT\_GUIDE/HANDLE\_ASSIST |
| demand\_id                | BIGINT       | NN, FK→demand.id      | 关联需求                         |
| title                     | VARCHAR(256) |                       | 会话标题                         |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE`       | ACTIVE / 归档状态                |
| asked\_target             | VARCHAR(64)  |                       | 已追问目标（引导进度）                  |
| created\_at / updated\_at | DATETIME(3)  | NN                    | 时间戳                          |

约束：`UNIQUE(demand_id, scene)` 名 `uk_agent_session_demand_scene`（0007 由 demand\_id 单列唯一改造而来）。

#### 3.4.3 `agent_message` — Agent 消息与幂等响应



| 列                   | 类型          | 约束                       | 说明                    |
| ------------------- | ----------- | ------------------------ | --------------------- |
| id                  | BIGINT      | PK                       | 主键                    |
| session\_id         | BIGINT      | NN, FK→agent\_session.id | 所属会话                  |
| role                | VARCHAR(16) | NN                       | user/assistant/system |
| content             | TEXT        | NN                       | 消息文本                  |
| structured\_payload | JSON        |                          | 结构化产出（追问 / 要素抽取 JSON） |
| request\_id         | VARCHAR(64) |                          | 客户端请求 ID（幂等）          |
| request\_hash       | VARCHAR(64) |                          | 请求哈希（重试返回同一响应）        |
| prompt\_version\_id | BIGINT      | FK→prompt\_version.id    | 本次应答使用的提示词快照          |
| model               | VARCHAR(64) |                          | 模型标识（方舟 endpoint）     |
| prompt\_tokens      | INT         |                          | 输入 token              |
| completion\_tokens  | INT         |                          | 输出 token              |
| latency\_ms         | INT         |                          | 响应耗时毫秒                |
| created\_at         | DATETIME(3) | NN                       | 创建时间                  |

约束：`UNIQUE(session_id, request_id, role)` 名 `uq_message_request_role`。

#### 3.4.4 `agent_draft` — 处理辅助 Agent 草稿区



| 列                         | 类型          | 约束                       | 说明                                                     |
| ------------------------- | ----------- | ------------------------ | ------------------------------------------------------ |
| id                        | BIGINT      | PK                       | 主键                                                     |
| demand\_id                | BIGINT      | NN, FK→demand.id         | 需求 ID（IDX `idx_agent_draft_demand`）                    |
| session\_id               | BIGINT      | NN, FK→agent\_session.id | 来源会话                                                   |
| draft\_type               | VARCHAR(16) | NN                       | QUESTIONS 调研问题 / SOLUTION 方案初稿                         |
| content                   | MEDIUMTEXT  | NN                       | 草稿 JSON（questions \[] 或 {specContent,solutionContent}） |
| status                    | VARCHAR(16) | NN, 默认 `PENDING`         | PENDING/CONFIRMED/DISCARDED                            |
| created\_by               | BIGINT      | NN, FK→dh\_user.id       | 生成操作人                                                  |
| confirmed\_by             | BIGINT      |                          | 确认 / 废弃操作人（软关联）                                        |
| confirmed\_at             | DATETIME(3) |                          | 确认 / 废弃时间                                              |
| target\_solution\_id      | BIGINT      |                          | 确认入库的 solution.id（软关联）                                 |
| created\_at / updated\_at | DATETIME(3) | NN                       | 时间戳                                                    |

#### 3.4.5 `rag_vector` — RAG 需求向量知识库

DONE 需求向量化，供处理辅助相似案例检索；应用内 L2 归一化向量，JSON 数组存 `MEDIUMTEXT`（无外部向量库）。



| 列                         | 类型           | 约束                                          | 说明                                           |
| ------------------------- | ------------ | ------------------------------------------- | -------------------------------------------- |
| id                        | BIGINT       | PK                                          | 主键                                           |
| demand\_id                | BIGINT       | NN, FK→demand.id, UQ `uk_rag_vector_demand` | 需求 ID（重复向量化幂等跳过）                             |
| demand\_no                | VARCHAR(40)  | NN                                          | 需求编号（冗余直出）                                   |
| title                     | VARCHAR(256) | NN                                          | 标题（冗余）                                       |
| demand\_type\_code        | VARCHAR(16)  |                                             | 类型码（冗余）                                      |
| content                   | MEDIUMTEXT   | NN                                          | 向量化原文（标题 + 描述 + 最新方案 + 评审意见）                 |
| embedding                 | MEDIUMTEXT   | NN                                          | 向量 JSON 数组（L2 归一化）                           |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE`                             | ACTIVE/INACTIVE（IDX `idx_rag_vector_status`） |
| vectorized\_at            | DATETIME(3)  | NN                                          | 向量化时间                                        |
| created\_at / updated\_at | DATETIME(3)  | NN                                          | 时间戳                                          |



***

### 3.5 通知与统计报表域

#### 3.5.1 `notification` — 站内信信箱（表实现，替代 MQ）

一期只写 IN\_APP 行，写入即送达；WECOM 渠道列保留二期。



| 列              | 类型           | 约束                 | 说明                                                   |
| -------------- | ------------ | ------------------ | ---------------------------------------------------- |
| id             | BIGINT       | PK                 | 主键                                                   |
| demand\_id     | BIGINT       |                    | 关联需求（系统通知可空；软关联，IDX `idx_demand`）                    |
| receiver\_id   | BIGINT       | NN, FK→dh\_user.id | 接收人（IDX `idx_receiver_unread(receiver_id, is_read)`） |
| channel        | VARCHAR(16)  | NN, 默认 `IN_APP`    | IN\_APP 站内 / WECOM 企微（二期）                            |
| template\_code | VARCHAR(64)  |                    | 模板编码（事件名 / SLA\_ALERT / REPORT\_READY）               |
| title          | VARCHAR(256) | NN                 | 标题（渲染后）                                              |
| content        | TEXT         |                    | 正文（渲染后）                                              |
| link           | VARCHAR(512) |                    | 跳转链接                                                 |
| is\_read       | TINYINT(1)   | NN, 默认 0           | 是否已读                                                 |
| read\_at       | DATETIME(3)  |                    | 阅读时间                                                 |
| send\_status   | VARCHAR(16)  | NN, 默认 `PENDING`   | PENDING/SENT/FAILED（IN\_APP 写入即 SENT）                |
| retry\_count   | INT          | NN, 默认 0           | 企微推送重试计数（二期）                                         |
| created\_at    | DATETIME(3)  | NN                 | 创建时间                                                 |
| sent\_at       | DATETIME(3)  |                    | 送达时间                                                 |

#### 3.5.2 `notification_template` — 通知模板



| 列                         | 类型           | 约束              | 说明                                      |
| ------------------------- | ------------ | --------------- | --------------------------------------- |
| id                        | BIGINT       | PK              | 主键                                      |
| template\_code            | VARCHAR(64)  | NN, UQ          | 模板编码（状态机事件名 / SLA\_ALERT/REPORT\_READY） |
| template\_name            | VARCHAR(128) | NN              | 模板名称                                    |
| title\_template           | VARCHAR(256) | NN              | 标题模板（`${var}` 占位，缺失变量渲染为空串）             |
| content\_template         | TEXT         | NN              | 正文模板                                    |
| status                    | VARCHAR(16)  | NN, 默认 `ACTIVE` | ACTIVE/INACTIVE                         |
| remark                    | VARCHAR(512) |                 | 备注                                      |
| created\_at / updated\_at | DATETIME(3)  | NN              | 时间戳                                     |

种子 19 条：SUBMIT/WITHDRAW/ACCEPT/RETURN/CLOSE/ASSIGN/CLAIM/SUBMIT\_REVIEW/REVIEW\_PASS/REVIEW\_REJECT/START/SUBMIT\_ACCEPTANCE/ACCEPT\_PASS/ACCEPT\_REJECT/CHANGE\_TYPE/HOLD/RESUME/SLA\_ALERT/REPORT\_READY。

#### 3.5.3 `notification_preference` — 用户通知偏好

TODO 待办提醒不可关闭、不落库。



| 列                         | 类型          | 约束                 | 说明                                                                           |
| ------------------------- | ----------- | ------------------ | ---------------------------------------------------------------------------- |
| id                        | BIGINT      | PK                 | 主键                                                                           |
| user\_id                  | BIGINT      | NN, FK→dh\_user.id | 用户                                                                           |
| notify\_type              | VARCHAR(32) | NN, UQ 组合          | STATUS\_CHANGE/MENTION/ASSIGN/REVIEW\_REQUEST/ACCEPTANCE\_REQUEST/SLA\_ALERT |
| enabled                   | TINYINT(1)  | NN, 默认 1           | 是否开启                                                                         |
| created\_at / updated\_at | DATETIME(3) | NN                 | 时间戳                                                                          |

约束：`UNIQUE(user_id, notify_type)` 名 `uk_user_type`。

#### 3.5.4 `notify_dedupe` — 通知去重（替代 Redis setIfAbsent + TTL）



| 列           | 类型           | 约束     | 说明                                        |
| ----------- | ------------ | ------ | ----------------------------------------- |
| id          | BIGINT       | PK     | 主键                                        |
| dedupe\_key | VARCHAR(128) | NN, UQ | 去重键，如 `sla:alert:RED:{demandId}:{status}` |
| created\_at | DATETIME(3)  | NN     | 标记时间（7 天过期由扫描侧判断）                         |

#### 3.5.5 `demand_stat_daily` — 需求日统计预聚合

看板实时 SQL 不读本表，仅落档；组织维度一期写 0。



| 列                  | 类型            | 约束              | 说明              |
| ------------------ | ------------- | --------------- | --------------- |
| id                 | BIGINT        | PK              | 主键              |
| stat\_date         | DATE          | NN, UQ 组合       | 统计日期            |
| demand\_type\_code | VARCHAR(32)   | NN, UQ 组合       | 需求类型            |
| assignee\_org\_id  | BIGINT        | NN, 默认 0, UQ 组合 | 承接组织（待组织域）      |
| reporter\_org\_id  | BIGINT        | NN, 默认 0, UQ 组合 | 提报组织（待组织域）      |
| status             | VARCHAR(32)   | NN, UQ 组合       | 状态              |
| cnt                | INT           | NN, 默认 0        | 数量              |
| avg\_cycle\_hours  | DECIMAL(10,2) |                 | 已关闭需求平均交付周期（小时） |
| updated\_at        | DATETIME(3)   | NN              | 刷新时间（ON UPDATE） |

约束：`UNIQUE(stat_date, demand_type_code, assignee_org_id, reporter_org_id, status)` 名 `uk_dim`。

#### 3.5.6 `report_export_task` — 报表导出异步任务（文件落本地目录，替代 MinIO）



| 列             | 类型           | 约束                 | 说明                                             |
| ------------- | ------------ | ------------------ | ---------------------------------------------- |
| id            | BIGINT       | PK                 | 主键                                             |
| task\_no      | VARCHAR(64)  | NN, UQ             | 任务编号 `RPT-YYYYMMDD-NNN`                        |
| report\_type  | VARCHAR(32)  | NN                 | DEMAND\_LIST 需求清单 / MONTHLY\_REVIEW 月度复盘（二期）   |
| params\_json  | TEXT         |                    | 导出筛选参数 JSON                                    |
| requester\_id | BIGINT       | NN, FK→dh\_user.id | 发起人（IDX `idx_requester(requester_id, status)`） |
| status        | VARCHAR(16)  | NN, 默认 `PENDING`   | PENDING/RUNNING/SUCCESS/FAILED                 |
| file\_path    | VARCHAR(512) |                    | 本地文件路径（`storage/reports/`）                     |
| file\_name    | VARCHAR(256) |                    | 文件名                                            |
| error\_msg    | VARCHAR(512) |                    | 失败原因                                           |
| created\_at   | DATETIME(3)  | NN                 | 创建时间                                           |
| finished\_at  | DATETIME(3)  |                    | 完成时间                                           |



***

## 4. 种子数据清单（随迁移初始化）



| 迁移   | 种子内容                                                                                                                            |
| ---- | ------------------------------------------------------------------------------------------------------------------------------- |
| 0005 | 初始 ADMIN 账号（login\_account=admin，密码取环境变量 `ADMIN_INITIAL_PASSWORD`，BCrypt 哈希，must\_change\_pwd=1；未配置则跳过）                         |
| 0006 | state\_machine\_config：DEFAULT 默认状态机全套规则（0009 已将角色重映射为 MANAGER/EXECUTIVE 口径）                                                    |
| 0008 | notification\_template 19 条；sla\_config 11 条（TECH/MATL/TRAIN）                                                                   |
| 0010 | demand\_org 11 个组织（100/110/111/112/120/121/130/131/140/141/900）；demand\_type 3 类；demand\_channel 8 个（2 个 ACTIVE）；sys\_dict 21 项 |
| 0014 | dh\_channel\_identity 存量回填：非 ACCOUNT 用户每人生成一条指向自己的渠道身份（INSERT IGNORE 幂等，非种子） |
| 0015 | 数据清洗：渠道临时人（channel != 'ACCOUNT'）的 phone 渠道快照脏数据统一置 NULL（无消费方），为唯一索引腾出空间 |



***

## 5. 外键与软关联汇总

### 5.1 数据库级外键（有 FK 约束）



| 子表。列                                                | 父表                                          |
| --------------------------------------------------- | ------------------------------------------- |
| refresh\_token.user\_id                             | dh\_user.id                                 |
| demand\_role\_grant.user\_id / granted\_by          | dh\_user.id                                 |
| dh\_channel\_identity.user\_id                     | dh\_user.id（OneID 归属人，0014）                 |
| demand.submitter\_id / assignee\_id                 | dh\_user.id                                 |
| demand.standard\_version\_id                        | prompt\_version.id                          |
| demand.split\_from\_id                              | demand.id（自引用）                              |
| demand\_change\_log.demand\_id / changed\_by        | demand.id / dh\_user.id                     |
| demand\_attachment.demand\_id / uploaded\_by        | demand.id / dh\_user.id                     |
| demand\_relation.from\_id / to\_id                  | demand.id（双向）                               |
| agent\_session.user\_id / demand\_id                | dh\_user.id / demand.id                     |
| agent\_message.session\_id / prompt\_version\_id    | agent\_session.id / prompt\_version.id      |
| agent\_draft.demand\_id / session\_id / created\_by | demand.id / agent\_session.id / dh\_user.id |
| rag\_vector.demand\_id                              | demand.id                                   |
| demand\_transition\_log.demand\_id / operator\_id   | demand.id / dh\_user.id                     |
| assignment.demand\_id / operator\_id                | demand.id / dh\_user.id                     |
| solution.demand\_id / author\_id                    | demand.id / dh\_user.id                     |
| review.demand\_id / target\_id / reviewer\_id       | demand.id / solution.id / dh\_user.id       |
| comment.demand\_id / author\_id                     | demand.id / dh\_user.id                     |
| effort\_log.demand\_id / user\_id                   | demand.id / dh\_user.id                     |
| notification.receiver\_id                           | dh\_user.id                                 |
| notification\_preference.user\_id                   | dh\_user.id                                 |
| report\_export\_task.requester\_id                  | dh\_user.id                                 |

### 5.2 无约束软关联（代码层保证，ER 图中用虚线表示）



| 子表。列                                                | 指向                                         | 原因                      |
| --------------------------------------------------- | ------------------------------------------ | ----------------------- |
| demand.session\_id                                  | agent\_session.id                          | 仅 UQ 无 FK（草稿先发、会话后补的场景） |
| demand.assignee\_org\_id / submitter\_org\_id       | demand\_org.id                             | 组织域一期只建不用               |
| demand\_type.default\_org\_id                       | demand\_org.id                             | 注册配置，避免组织维护受 FK 约束      |
| demand\_org.parent\_id                              | demand\_org.id                             | 物化路径邻接关系，代码维护           |
| assignment.from\_user\_id / to\_user\_id            | dh\_user.id                                | 历史人员可能删号，仅作记录           |
| notification.demand\_id                             | demand.id                                  | 信箱允许需求侧无感知写入            |
| agent\_draft.confirmed\_by / target\_solution\_id   | dh\_user.id / solution.id                  | 确认动作可能滞后 / 废弃           |
| demand\_role\_grant.org\_id                         | demand\_org.id                             | 预留                      |
| dh\_identity\_link\_log.identity\_id（及人员列）        | dh\_channel\_identity.id / dh\_user.id      | 审计快照，行只增不改，避免约束牵连      |
| demand\_channel\_whitelist.created\_by               | dh\_user.id                                | 操作人仅作记录                 |
| demand\_channel\_whitelist（channel\_code）            | demand\_channel.channel\_code              | 渠道码字符串契约               |
| channel\_dept\_unmapped（channel\_code）              | demand\_channel.channel\_code              | 渠道码字符串契约                |
| demand.demand\_type\_code / subtype\_code / channel | demand\_type / sys\_dict / demand\_channel | 编码字符串契约，字典 / 类型可启停不影响历史 |



***

## 6. 设计要点小结



1. **需求单表为中心**：草稿与正式需求同表（`status=DRAFT`、`demand_no` 可空），五区要素用 `elements/ext/quality` 三个 JSON 承载，标准版本快照绑定，类型扩展零 DDL。

2. **状态机数据库化**：规则在 `state_machine_config`，热重载；所有流转经引擎行锁串行化并追加 `demand_transition_log`，业务代码被禁止直接改 `demand.status`。

3. **全链路留痕**：要素变更（change\_log）、状态流转（transition\_log）、评审（review）、分派（assignment）均只追加不可改；快照列（姓名 / 部门 / 操作人）保证历史可回溯。

4. **幂等设计**：需求创建 `uq_demand_create` + 请求哈希、消息 `uq_message_request_role`、RAG 需求唯一、发号按日流水、通知 dedupe 表替代 Redis。

5. **无外部中间件依赖**：通知用信箱表替 MQ、去重替 Redis、文件落本地目录替 MinIO、向量 JSON 替向量库，MVP 只依赖 MySQL 即可运行。

6. **多租户 / 多渠道接缝**：渠道注册、组织树物化路径、渠道部门未映射校准清单支持外部渠道（创金零售小程序）票据登录与部门映射。

7. **OneID 身份一期（0014/0015）**：渠道身份与用户档案分离（`dh_channel_identity` 独立成表），归并唯一手段是管理员挂接（不做手机号自动撮合、不做自助绑定），挂接 / 改挂全程审计留痕；`dh_user.phone` 全表唯一后可作登录账号，管理员判定收敛为 `role='ADMIN'` 唯一口径（config 企微管理员白名单过渡机制退役）；渠道白名单（0011）与 OneID 正交：白名单管「允许谁进」，OneID 管「进来的是谁」。

8. **排序规则注意**：`dh_channel_identity` 按 `channel_user_id` 与 `dh_user.wecom_userid` 关联时混用 `utf8mb4_0900_ai_ci` 会报 Illegal mix of collations，故建表排序规则跟随 dh\_user 的 `utf8mb4_unicode_ci`。