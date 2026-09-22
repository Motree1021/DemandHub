# DemandHub 零售业务线需求管理系统・系统数据库设计

| 项目   | 内容                                    |
| ---- | ------------------------------------- |
| 文档名称 | DemandHub 系统数据库设计                     |
| 版本   | v1.4                                  |
| DBMS | MySQL 8.0（InnoDB，utf8mb4）             |
| 编制部门 | 财管科技产品部                               |
| 编制日期 | 2026-09-19                            |
| 上游文档 | 概念模型 v1.2、BRD v1.3、SRS v1.4、架构设计 v1.3、H5 嵌入对接标准 v2.0 |



***

## 1. 设计约定



1. **主键**：统一 `BIGINT UNSIGNED` 自增主键 `id`，业务编号单独字段（如 `demand_no`）并建唯一索引。

2. **公共字段**：所有业务表含 `created_at / created_by / updated_at / updated_by / is_deleted / version`。

3. **软删除**：`is_deleted TINYINT(1) DEFAULT 0`，查询默认过滤。

4. **时间**：`DATETIME(3)`，时区统一 Asia/Shanghai，应用层写入。

5. **金额 / 数量**：本系统无金额；数量类用 `INT`，工时用 `DECIMAL(5,1)`。

6. **组织树**：`demand_org` 用 `parent_id` 自关联 + `path` 物化路径（如 `/1/15/128/`）便于子树查询；DemandHub 管理员可在后台维护组织树（增删改），创金零售渠道回流的部门信息作为初始数据与日常校准。

7. **状态 / 类型**：用 `VARCHAR(32)` 存枚举码，字典表维护中文名，不使用 MySQL ENUM（便于扩展）。

8. **扩展表**：需求基表 `demand` + 类型扩展表（`demand_ext_tech/material/training`），共享主键 `demand_id`（1:1）。

9. **索引**：外键字段必建索引；高频查询组合字段建联合索引；不建过度索引。

10. **审计**：流转日志、评论、通知只增不改。



***

## 2. ER 总览（实体关系）



```
【渠道接入】
demand_channel（渠道注册表：创金零售SSO/企微机器人/飞书机器人/豆包工作/WorkBuddy；一期仅启用创金零售）
channel_user_mapping（渠道用户ID → DemandHub OneID，存渠道回调原始信息快照）

【DemandHub 自有主数据】
demand_user ──> demand_org（经 primary_org_id 关联，员工挂组织，外部用户挂外部虚拟组织）

【业务角色：DemandHub 本地维护】
demand_role_grant（user_id × role_code × org_id × type_scope）

demand_user ─┬─< demand (提报人/代办人/处理人/操作人)
              ├─< assignment
              ├─< demand_transition_log
              ├─< solution
              │         └─< review
              ├─< effort_log
              ├─< comment
              └─< notification

demand ─┬─ N:1 ─ demand_type
        ├─ 1:1 ─ demand_ext_tech / demand_ext_material / demand_ext_training
        ├─ 1:N ─ assignment
        ├─ 1:N ─ demand_transition_log
        ├─ 1:N ─ solution
        │         └─ 1:N ─ review
        ├─ 1:N ─ effort_log
        ├─ 1:N ─ comment
        ├─ 1:N ─ attachment (通用挂接 biz_type+biz_id)
        ├─ N:1 ─ project
        ├─ N:M 自关联 ─ demand_relation
        └─ 1:1 ─ demand_draft

project ─ 1:N ─ project_milestone

agent_session (Agent 对话，独立)
demand_stat_daily (预聚合统计，独立)
```

> 设计边界：DemandHub 拥有自有用户体系（OneID）与组织树，管理员可在后台维护；各提报渠道自行鉴权，DemandHub 经渠道服务端接口回源核验（一期为创金零售 SSO 票据 verify），经 `channel_user_mapping` 自动匹配（企微 userid > 手机号）或人工绑定到 DemandHub OneID；DemandHub 不直接对接企微接口。



***

## 3. 表结构详细设计

### 3.1 渠道接入、自有用户与业务角色域

> **设计原则**：DemandHub 拥有自有用户体系（OneID）与组织树；一期创金零售渠道以一次性 SSO 票据回源核验身份，PC 管理端用账号密码登录；核验后经 `channel_user_mapping` 自动匹配（企微 userid > 手机号）或人工绑定到 OneID；DemandHub 不直接对接企微接口。

#### 3.1.1 `demand_channel` 渠道注册表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INC | |
| channel_code | VARCHAR(32) | UNIQUE | WEB / CHUANGJIN_LS / WECOM_BOT / FEISHU_BOT / DOUBAO_WORK / WORKBUDDY / VOICE（WECOM_APP 预留，一期 DISABLED） |
| channel_name | VARCHAR(64) | NOT NULL | 渠道中文名 |
| app_id | VARCHAR(128) | | 渠道侧应用 ID（机器人/外部应用标识；创金零售 SSO 渠道留空） |
| callback_enabled | TINYINT(1) | NOT NULL DEFAULT 1 | 是否启用回调接收需求 |
| status | VARCHAR(16) | NOT NULL DEFAULT 'ACTIVE' | ACTIVE / DISABLED |
| config_json | JSON | | 渠道配置（SSO 校验接口 base_url、app_key、加密 app_secret、票据 TTL；密钥加密存储、接口脱敏） |
| created_at / updated_at | | | |

> 新渠道接入 = 加一行配置 + 写一个渠道适配器（票据校验/回调），不改表结构。一期仅启用 CHUANGJIN_LS（H5）与内置 WEB（PC 账密），WECOM_APP/机器人等预留 DISABLED。

#### 3.1.2 `demand_user` DemandHub 自有用户表（OneID）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INC | DemandHub OneID |
| name | VARCHAR(64) | NOT NULL | 姓名 |
| phone | VARCHAR(32) | UNIQUE | 手机号（脱敏存储，选填，辅助匹配键） |
| wecom_userid | VARCHAR(64) | UNIQUE | 企微 userid（verify 必填回传，首选匹配/建号主键） |
| employee_no | VARCHAR(32) | | 工号（员工才有） |
| email | VARCHAR(128) | | 邮箱 |
| is_employee | TINYINT(1) | NOT NULL DEFAULT 0 | 1=员工，0=外部用户 |
| primary_org_id | BIGINT UNSIGNED | FK→demand_org.id | 主组织（员工挂组织树，外部用户挂"外部/待确认"虚拟组织） |
| status | VARCHAR(16) | NOT NULL DEFAULT 'PENDING' | PENDING（待管理员完善）/ ACTIVE / DISABLED / MERGED |
| merged_to_user_id | BIGINT UNSIGNED | NULL | 合并指向的 OneID（status=MERGED 时有效） |
| last_login_channel | VARCHAR(32) | | 最近登录渠道 |
| last_login_at | DATETIME(3) | | 最近登录时间 |
| created_at / updated_at | | | |

索引：`uk_phone(phone)`、`uk_wecom_userid(wecom_userid)`、`idx_primary_org(primary_org_id)`、`idx_status(status)`、`idx_is_employee(is_employee)`。

> 新渠道用户首次核验时：企微 userid（必填主键）/手机号（选填）命中已有 OneID 则直接建映射；未命中时，创金零售票据有效且带回企微 userid 的自动建 ACTIVE 员工账号（手机/部门缺失不阻塞；部门按 dept_id 经 external_dept_id 映射，未映射挂“未分配组织”虚拟节点）；仅外部渠道身份不全的用户才建 PENDING 记录进管理员“待完善”队列，创金零售渠道缺必填 user_id/name 属协议错误（40005），拒绝登录且不建号。重复 OneID 执行合并，原记录置 MERGED 并迁移数据。

#### 3.1.3 `demand_org` 组织节点表（管理员可 CRUD）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INC | |
| name | VARCHAR(128) | NOT NULL | 组织名称 |
| level | VARCHAR(16) | NOT NULL | LINE / DEPT / GROUP |
| parent_id | BIGINT UNSIGNED | NOT NULL DEFAULT 0 | 父节点（引用本表 id），根 = 0 |
| path | VARCHAR(512) | NOT NULL | 物化路径，如 `/1/15/128/` |
| org_kind | VARCHAR(16) | | REPORTER / ASSIGNER / BOTH |
| external_flag | TINYINT(1) | NOT NULL DEFAULT 0 | 是否外部虚拟组织（如"外部合作方""待确认"） |
| external_dept_id | VARCHAR(32) | | 渠道侧部门 ID（创金零售/企微部门 ID），票据登录部门映射用 |
| status | VARCHAR(16) | NOT NULL DEFAULT 'ACTIVE' | ACTIVE / DISABLED |
| created_at / updated_at | | | |

索引：`idx_parent(parent_id)`、`idx_path(path)`、`idx_status(status)`。

> 管理员在后台维护组织树；创金零售渠道回流的部门名用于初始化与日常校准匹配。部门拆分/合并直接调整节点层级与成员归属，不改流程规则。

#### 3.1.4 `channel_user_mapping` 渠道用户映射表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INC | |
| channel_code | VARCHAR(32) | NOT NULL, FK→demand_channel | 渠道 |
| channel_user_id | VARCHAR(128) | NOT NULL | 渠道侧用户唯一 ID |
| demand_user_id | BIGINT UNSIGNED | NOT NULL, FK→demand_user.id | 映射到的 DemandHub OneID |
| channel_name | VARCHAR(64) | | 渠道回调的姓名快照 |
| channel_phone | VARCHAR(32) | | 渠道回调的手机号快照 |
| channel_dept | VARCHAR(256) | | 渠道回调的部门快照（可空，个人用户无部门） |
| match_type | VARCHAR(16) | NOT NULL | PHONE（手机号自动匹配）/ WECOMID（企微userid自动匹配）/ MANUAL（人工绑定） |
| bound_at | DATETIME(3) | | 绑定时间 |
| created_at / updated_at | | | |

索引：`uk_channel_user(channel_code, channel_user_id)`、`idx_demand_user(demand_user_id)`、`idx_match_type(match_type)`。

> 一个 DemandHub OneID 可绑定多个渠道（同一员工从企微、飞书、豆包工作多端登录）；一个渠道用户ID只绑定一个 OneID。

#### 3.1.5 `demand_role_grant` 业务角色授权表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT UNSIGNED PK | |
| demand_user_id | BIGINT UNSIGNED NOT NULL | 引用 demand_user.id |
| role_code | VARCHAR(32) NOT NULL | 见下方角色枚举 |
| org_id | BIGINT UNSIGNED NULL | 授权组织范围（引用 demand_org.id，空 = 不限） |
| demand_type_scope | VARCHAR(256) | 覆盖类型范围，逗号分隔；空 = 跟随角色默认 |
| effective_from | DATETIME(3) | 生效起 |
| effective_to | DATETIME(3) NULL | 生效止 |
| granted_by | BIGINT UNSIGNED | 授予人（demand_user.id） |
| created_at / updated_at | | |

索引：`uk_grant(demand_user_id, role_code, org_id, demand_type_scope, is_deleted)`、`idx_org(org_id)`、`idx_role(role_code)`。

> 业务角色编码固定为：
> - ADMIN（系统管理员）
> - EXECUTIVE（需求管理者，零售线领导）
> - TECH_MANAGER / MATL_MANAGER / TRAIN_MANAGER（科技/物料/培训需求经理）
> - TECH_HANDLER / MATL_HANDLER / TRAIN_HANDLER（科技/物料/培训需求处理人）
>
> 不设"需求提报人"角色——任何登录用户默认可提报需求。一个用户可拥有多条授权（如既是科技处理人又是物料经理）。



***

### 3.2 需求域

#### 3.2.1 `demand_type` 需求类型字典表



| 字段                  | 类型                 | 说明                                           |
| ------------------- | ------------------ | -------------------------------------------- |
| id                  | BIGINT UNSIGNED PK |                                              |
| type\_code          | VARCHAR(32) UNIQUE | TECH / MATL / TRAIN                          |
| type\_name          | VARCHAR(64)        | 科技需求 / 物料需求 / 培训需求                           |
| parent\_type\_code  | VARCHAR(32)        | 子类（如 SYSTEM\_DEV / REPORT / INTEGRATION ...） |
| default\_org\_id    | BIGINT UNSIGNED    | 默认承接组织                                       |
| state\_machine\_key | VARCHAR(64)        | 关联状态机配置 key                                  |
| sla\_config         | JSON               | 各状态 SLA 配置                                   |
| sort                | INT                |                                              |
| status              | VARCHAR(16)        | ACTIVE / DISABLED                            |

#### 3.2.2 `demand` 需求基表



| 字段                                                                            | 类型                                     | 说明                                                                                                         |
| ----------------------------------------------------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| id                                                                            | BIGINT UNSIGNED PK                     |                                                                                                            |
| demand\_no                                                                    | VARCHAR(40) UNIQUE                     | 业务编号 TECH-20260919-001                                                                                     |
| title                                                                         | VARCHAR(256) NOT NULL                  | 标题                                                                                                         |
| demand\_type\_code                                                            | VARCHAR(32) NOT NULL, FK→demand\_type  |                                                                                                            |
| subtype\_code                                                                 | VARCHAR(32)                            | 子类编码                                                                                                       |
| content                                                                       | TEXT NOT NULL                          | 需求描述                                                                                                       |
| urgency                                                                       | VARCHAR(16)                            | NORMAL / URGENT / CRITICAL                                                                                 |
| status                                                                        | VARCHAR(32) NOT NULL                   | DRAFT/SUBMITTED/NEED\_INFO/TRIAGE/ANALYZING/SOLUTION\_REVIEW/CONFIRMED/IN\_PROGRESS/ACCEPTANCE/DONE/CLOSED |
| on\_hold                                                                      | TINYINT(1) DEFAULT 0                   | 挂起叠加态                                                                                                      |
| hold\_reason                                                                  | VARCHAR(256)                           |                                                                                                            |
| hold\_snapshot\_status                                                        | VARCHAR(32)                            | 挂起前主状态                                                                                                     |
| submitter\_id                                                                 | BIGINT UNSIGNED NOT NULL, FK→sys\_user | 提报人（代办人）                                                                                                   |
| actual\_demander\_id                                                          | BIGINT UNSIGNED, FK→sys\_user          | 实际需求人                                                                                                      |
| submitter\_org\_id                                                            | BIGINT UNSIGNED                        | 提报人部门快照                                                                                                    |
| submitter\_org\_snapshot                                                      | VARCHAR(256)                           | 提报人部门名称快照                                                                                                  |
| channel                                                                       | VARCHAR(32)                            | WEB / CHUANGJIN\_LS / WECOM\_BOT / VOICE                                                                       |
| assignee\_org\_id                                                             | BIGINT UNSIGNED                        | 承接组织                                                                                                       |
| assignee\_user\_id                                                            | BIGINT UNSIGNED                        | 当前处理人                                                                                                      |
| project\_id                                                                   | BIGINT UNSIGNED NULL, FK→project       | 关联项目                                                                                                       |
| expect\_delivery\_at                                                          | DATETIME                               | 期望交付时间                                                                                                     |
| actual\_delivery\_at                                                          | DATETIME                               | 实际交付时间                                                                                                     |
| submitted\_at                                                                 | DATETIME                               | 提交时间                                                                                                       |
| closed\_at                                                                    | DATETIME                               | 关闭时间                                                                                                       |
| close\_reason                                                                 | VARCHAR(256)                           |                                                                                                            |
| quality\_score                                                                | TINYINT                                | 1-5                                                                                                        |
| satisfaction\_score                                                           | TINYINT                                | 1-5                                                                                                        |
| created\_at / created\_by / updated\_at / updated\_by / is\_deleted / version |                                        |                                                                                                            |

索引：



* `uk_demand_no(demand_no)`

* `idx_status(status)`

* `idx_type_status(demand_type_code, status)`

* `idx_submitter(submitter_id)`

* `idx_assignee_org(assignee_org_id, status)`

* `idx_assignee_user(assignee_user_id, status)`

* `idx_project(project_id)`

* `idx_submitted_at(submitted_at)`

#### 3.2.3 `demand_ext_tech` 科技需求扩展表（1:1）



| 字段                        | 类型                               |
| ------------------------- | -------------------------------- |
| demand\_id                | BIGINT UNSIGNED PK, FK→demand.id |
| related\_system           | VARCHAR(128)                     |
| related\_module           | VARCHAR(128)                     |
| business\_scenario        | TEXT                             |
| acceptance\_criteria      | TEXT                             |
| created\_at / updated\_at |                                  |

#### 3.2.4 `demand_ext_material` 物料需求扩展表（1:1）



| 字段                    | 类型                               |
| --------------------- | -------------------------------- |
| demand\_id            | BIGINT UNSIGNED PK, FK→demand.id |
| material\_subtype     | VARCHAR(64)                      |
| usage\_scenario       | VARCHAR(256)                     |
| quantity              | INT                              |
| expected\_arrival\_at | DATETIME                         |

#### 3.2.5 `demand_ext_training` 培训需求扩展表（1:1）



| 字段                     | 类型                               |
| ---------------------- | -------------------------------- |
| demand\_id             | BIGINT UNSIGNED PK, FK→demand.id |
| training\_subtype      | VARCHAR(64)                      |
| trainee\_object        | VARCHAR(128)                     |
| trainee\_count         | INT                              |
| expected\_complete\_at | DATETIME                         |

#### 3.2.6 `demand_relation` 需求关联表



| 字段                  | 类型                 | 说明                                   |
| ------------------- | ------------------ | ------------------------------------ |
| id                  | BIGINT UNSIGNED PK |                                      |
| demand\_id          | BIGINT UNSIGNED FK | 主需求                                  |
| related\_demand\_id | BIGINT UNSIGNED FK | 关联需求                                 |
| relation\_type      | VARCHAR(16)        | PARENT / DEPENDS / DUPLICATE / SPLIT |

唯一索引：`uk_pair(demand_id, related_demand_id, relation_type)`。

#### 3.2.7 `demand_draft` 草稿 / 提报会话表



| 字段                        | 类型                           | 说明             |
| ------------------------- | ---------------------------- | -------------- |
| id                        | BIGINT UNSIGNED PK           |                |
| user\_id                  | BIGINT UNSIGNED FK           |                |
| channel                   | VARCHAR(32)                  |                |
| conversation              | JSON                         | Agent 对话记录     |
| voice\_transcript         | TEXT                         | 语音转写文本         |
| form\_payload             | JSON                         | 已回填的表单字段       |
| converted\_demand\_id     | BIGINT UNSIGNED NULL, UNIQUE | 转化后的需求 id（1:1） |
| created\_at / updated\_at |                              |                |

#### 3.2.8 `attachment` 附件表（通用挂接）



| 字段           | 类型                 | 说明                                  |
| ------------ | ------------------ | ----------------------------------- |
| id           | BIGINT UNSIGNED PK |                                     |
| biz\_type    | VARCHAR(32)        | DEMAND / SOLUTION / COMMENT / DRAFT |
| biz\_id      | BIGINT UNSIGNED    | 业务 id                               |
| file\_name   | VARCHAR(256)       | 原始文件名                               |
| file\_path   | VARCHAR(512)       | 对象存储路径                              |
| file\_size   | BIGINT             | 字节                                  |
| mime\_type   | VARCHAR(128)       |                                     |
| ext          | VARCHAR(16)        | 扩展名                                 |
| transcript   | TEXT               | 语音转写文本                              |
| uploaded\_by | BIGINT UNSIGNED    |                                     |
| created\_at  |                    |                                     |

索引：`idx_biz(biz_type, biz_id)`。



***

### 3.3 处理与流转域

#### 3.3.1 `assignment` 处理任务表



| 字段                        | 类型                   | 说明                       |
| ------------------------- | -------------------- | ------------------------ |
| id                        | BIGINT UNSIGNED PK   |                          |
| demand\_id                | BIGINT UNSIGNED FK   |                          |
| org\_id                   | BIGINT UNSIGNED      | 承接组织                     |
| assignee\_id              | BIGINT UNSIGNED NULL | 处理人（空 = 待领取池）            |
| dispatcher\_id            | BIGINT UNSIGNED      | 分发人                      |
| assign\_mode              | VARCHAR(16)          | DISPATCH / CLAIM         |
| status                    | VARCHAR(16)          | OPEN / PROCESSING / DONE |
| assigned\_at              | DATETIME             | 分发时间                     |
| claimed\_at               | DATETIME             | 领取时间                     |
| finished\_at              | DATETIME             | 完成时间                     |
| created\_at / updated\_at |                      |                          |

索引：`idx_demand(demand_id)`、`idx_org_status(org_id, status)`、`idx_assignee(assignee_id, status)`。

#### 3.3.2 `demand_transition_log` 流转日志表（只增不改）



| 字段                 | 类型                 |
| ------------------ | ------------------ |
| id                 | BIGINT UNSIGNED PK |
| demand\_id         | BIGINT UNSIGNED FK |
| from\_status       | VARCHAR(32)        |
| to\_status         | VARCHAR(32)        |
| action             | VARCHAR(64)        |
| operator\_id       | BIGINT UNSIGNED    |
| operator\_snapshot | VARCHAR(128)       |
| comment            | TEXT               |
| extra              | JSON               |
| created\_at        | DATETIME           |

索引：`idx_demand(demand_id, created_at)`。

#### 3.3.3 `solution` 需求方案表（多版本）



| 字段                        | 类型                 | 说明                                      |
| ------------------------- | ------------------ | --------------------------------------- |
| id                        | BIGINT UNSIGNED PK |                                         |
| demand\_id                | BIGINT UNSIGNED FK |                                         |
| version                   | INT                | 版本号                                     |
| author\_id                | BIGINT UNSIGNED    |                                         |
| spec\_content             | TEXT               | 需求规约                                    |
| solution\_content         | TEXT               | 方案内容                                    |
| plan\_delivery\_at        | DATETIME           | 计划交付时间                                  |
| actual\_delivery\_at      | DATETIME           | 实际交付时间                                  |
| status                    | VARCHAR(16)        | DRAFT / REVIEWING / APPROVED / REJECTED |
| remark                    | VARCHAR(512)       |                                         |
| created\_at / updated\_at |                    |                                         |

唯一索引：`uk_demand_version(demand_id, version)`。

#### 3.3.4 `review` 评审 / 验收表



| 字段             | 类型                       | 说明                    |
| -------------- | ------------------------ | --------------------- |
| id             | BIGINT UNSIGNED PK       |                       |
| demand\_id     | BIGINT UNSIGNED FK       |                       |
| solution\_id   | BIGINT UNSIGNED NULL, FK | 关联方案（验收时为空）           |
| review\_type   | VARCHAR(16)              | SOLUTION / ACCEPTANCE |
| reviewer\_id   | BIGINT UNSIGNED          |                       |
| conclusion     | VARCHAR(16)              | PASS / REJECT         |
| quality\_score | TINYINT                  | 1-5                   |
| comment        | TEXT                     | 意见                    |
| reviewed\_at   | DATETIME                 |                       |

索引：`idx_demand(demand_id, review_type)`。

#### 3.3.5 `effort_log` 工时记录表



| 字段                        | 类型                 |
| ------------------------- | ------------------ |
| id                        | BIGINT UNSIGNED PK |
| demand\_id                | BIGINT UNSIGNED FK |
| user\_id                  | BIGINT UNSIGNED    |
| hours                     | DECIMAL(5,1)       |
| work\_date                | DATE               |
| description               | VARCHAR(512)       |
| created\_at / updated\_at |                    |

索引：`idx_demand(demand_id)`、`idx_user_date(user_id, work_date)`。

#### 3.3.6 `comment` 评论沟通表



| 字段                   | 类型                 |
| -------------------- | ------------------ |
| id                   | BIGINT UNSIGNED PK |
| demand\_id           | BIGINT UNSIGNED FK |
| author\_id           | BIGINT UNSIGNED    |
| content              | TEXT               |
| mentioned\_user\_ids | VARCHAR(512)       |
| created\_at          |                    |

索引：`idx_demand(demand_id, created_at)`。



***

### 3.4 项目域

#### 3.4.1 `project` 项目表



| 字段                                                | 类型                 |
| ------------------------------------------------- | ------------------ |
| id                                                | BIGINT UNSIGNED PK |
| name                                              | VARCHAR(256)       |
| owner\_id                                         | BIGINT UNSIGNED    |
| status                                            | VARCHAR(16)        |
| started\_at                                       | DATETIME           |
| ended\_at                                         | DATETIME           |
| created\_at / updated\_at / is\_deleted / version |                    |

#### 3.4.2 `project_milestone` 项目里程碑表



| 字段          | 类型                 |
| ----------- | ------------------ |
| id          | BIGINT UNSIGNED PK |
| project\_id | BIGINT UNSIGNED FK |
| name        | VARCHAR(128)       |
| plan\_at    | DATETIME           |
| actual\_at  | DATETIME           |
| status      | VARCHAR(16)        |

索引：`idx_project(project_id)`。



***

### 3.5 通知域

#### 3.5.1 `notification` 通知消息表



| 字段                     | 类型                   | 说明                      |
| ---------------------- | -------------------- | ----------------------- |
| id                     | BIGINT UNSIGNED PK   |                         |
| demand\_id             | BIGINT UNSIGNED NULL |                         |
| receiver\_id           | BIGINT UNSIGNED      | 接收人                     |
| channel                | VARCHAR(16)          | IN\_APP / WECOM         |
| template\_code         | VARCHAR(64)          | 模板编码                    |
| title                  | VARCHAR(256)         |                         |
| content                | TEXT                 |                         |
| link                   | VARCHAR(512)         | 跳转链接                    |
| is\_read               | TINYINT(1) DEFAULT 0 |                         |
| read\_at               | DATETIME             |                         |
| send\_status           | VARCHAR(16)          | PENDING / SENT / FAILED |
| retry\_count           | INT DEFAULT 0        |                         |
| created\_at / sent\_at |                      |                         |

索引：`idx_receiver_unread(receiver_id, is_read)`、`idx_demand(demand_id)`。



***

### 3.6 支撑表

#### 3.6.1 `agent_session` Agent 会话表



| 字段                        | 类型                   |
| ------------------------- | -------------------- |
| id                        | BIGINT UNSIGNED PK   |
| user\_id                  | BIGINT UNSIGNED      |
| scene                     | VARCHAR(32)          |
| demand\_id                | BIGINT UNSIGNED NULL |
| trace\_id                 | VARCHAR(64)          |
| messages                  | JSON                 |
| created\_at / updated\_at |                      |

#### 3.6.2 `demand_stat_daily` 预聚合统计表



| 字段                 | 类型                 | 说明       |
| ------------------ | ------------------ | -------- |
| id                 | BIGINT UNSIGNED PK |          |
| stat\_date         | DATE               | 统计日期     |
| demand\_type\_code | VARCHAR(32)        |          |
| assignee\_org\_id  | BIGINT UNSIGNED    |          |
| reporter\_org\_id  | BIGINT UNSIGNED    |          |
| status             | VARCHAR(32)        |          |
| cnt                | INT                | 当日数量     |
| avg\_cycle\_hours  | DECIMAL(10,2)      | 平均周期（小时） |
| updated\_at        |                    |          |

唯一索引：`uk_dim(stat_date, demand_type_code, assignee_org_id, reporter_org_id, status)`。

#### 3.6.3 `sys_dict` 通用字典表



| 字段         | 类型                 |
| ---------- | ------------------ |
| id         | BIGINT UNSIGNED PK |
| dict\_type | VARCHAR(64)        |
| item\_code | VARCHAR(64)        |
| item\_name | VARCHAR(128)       |
| sort       | INT                |
| status     | VARCHAR(16)        |



***

## 4. 建表 DDL（MySQL 8.0）



```
\-- =========================================================

\-- DemandHub DDL v1.1  MySQL 8.0  InnoDB  utf8mb4\_0900\_ai\_ci

\-- =========================================================

SET NAMES utf8mb4;

SET FOREIGN\_KEY\_CHECKS = 0;

\-- ---------- 公共字段通用模板：

\-- created\_at      DATETIME(3)    NOT NULL DEFAULT CURRENT\_TIMESTAMP(3)

\-- created\_by      BIGINT UNSIGNED NOT NULL DEFAULT 0

\-- updated\_at      DATETIME(3)    NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3)

\-- updated\_by      BIGINT UNSIGNED NOT NULL DEFAULT 0

\-- is\_deleted      TINYINT(1)     NOT NULL DEFAULT 0

\-- version         INT            NOT NULL DEFAULT 0

\-- ---------- 渠道接入、自有用户与业务角色 ----------

CREATE TABLE demand_channel (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  channel_code    VARCHAR(32)  NOT NULL,
  channel_name    VARCHAR(64)  NOT NULL,
  app_id          VARCHAR(128) NULL,
  callback_enabled TINYINT(1)  NOT NULL DEFAULT 1,
  status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  config_json     JSON         NULL,
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_channel_code (channel_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='提报渠道注册表';

CREATE TABLE demand_user (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name                VARCHAR(64)  NOT NULL,
  login_name          VARCHAR(64)  NULL COMMENT 'PC登录账号',
  password_hash       VARCHAR(100) NULL COMMENT 'BCrypt密码哈希（仅PC账号密码登录）',
  password_updated_at DATETIME(3)  NULL,
  phone               VARCHAR(32)  NULL,
  wecom_userid        VARCHAR(64)  NULL COMMENT '创金零售verify回传的企微userid',
  employee_no         VARCHAR(32)  NULL,
  email               VARCHAR(128) NULL,
  is_employee         TINYINT(1)   NOT NULL DEFAULT 0,
  primary_org_id      BIGINT UNSIGNED NULL,
  status              VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
  merged_to_user_id   BIGINT UNSIGNED NULL,
  last_login_channel  VARCHAR(32)  NULL,
  last_login_at       DATETIME(3)  NULL,
  created_at          DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at          DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_login_name (login_name),
  UNIQUE KEY uk_phone (phone),
  UNIQUE KEY uk_wecom_userid (wecom_userid),
  KEY idx_primary_org (primary_org_id),
  KEY idx_status (status),
  KEY idx_is_employee (is_employee)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DemandHub自有用户OneID';

CREATE TABLE demand_org (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name            VARCHAR(128) NOT NULL,
  level           VARCHAR(16)  NOT NULL COMMENT 'LINE/DEPT/GROUP',
  parent_id       BIGINT UNSIGNED NOT NULL DEFAULT 0,
  path            VARCHAR(512) NOT NULL,
  org_kind        VARCHAR(16)  NULL COMMENT 'REPORTER/ASSIGNER/BOTH',
  external_dept_id VARCHAR(32) NULL COMMENT '渠道侧部门ID（创金零售/企微部门ID）',
  external_flag   TINYINT(1)   NOT NULL DEFAULT 0,
  status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_parent (parent_id),
  KEY idx_path (path),
  KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='组织树（管理员可CRUD）';

CREATE TABLE channel_user_mapping (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  channel_code    VARCHAR(32)  NOT NULL,
  channel_user_id VARCHAR(128) NOT NULL,
  demand_user_id  BIGINT UNSIGNED NOT NULL,
  channel_name    VARCHAR(64)  NULL,
  channel_phone   VARCHAR(32)  NULL,
  channel_dept    VARCHAR(256) NULL,
  match_type      VARCHAR(16)  NOT NULL COMMENT 'PHONE/WECOMID/MANUAL',
  bound_at        DATETIME(3)  NULL,
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_channel_user (channel_code, channel_user_id),
  KEY idx_demand_user (demand_user_id),
  KEY idx_match_type (match_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='渠道用户到OneID映射';

CREATE TABLE demand_role_grant (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_user_id      BIGINT UNSIGNED NOT NULL,
  role_code           VARCHAR(32)  NOT NULL COMMENT '角色族: ADMIN/EXECUTIVE/MANAGER/HANDLER；管哪类由 demand_type_scope 表达，管哪片由 org_id 子树表达',
  org_id              BIGINT UNSIGNED NULL,
  demand_type_scope   VARCHAR(256) NULL,
  effective_from      DATETIME(3) NULL,
  effective_to        DATETIME(3) NULL,
  granted_by          BIGINT UNSIGNED NULL,
  is_deleted          TINYINT(1)  NOT NULL DEFAULT 0,
  created_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_grant (demand_user_id, role_code, org_id, demand_type_scope, is_deleted),
  KEY idx_org (org_id),
  KEY idx_role (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务角色本地授权';

-- ---------- 需求域 ----------

CREATE TABLE demand\_type (

&#x20; id               BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; type\_code        VARCHAR(32) NOT NULL,

&#x20; type\_name        VARCHAR(64) NOT NULL,

&#x20; parent\_type\_code VARCHAR(32) NULL,

&#x20; default\_org\_id   BIGINT UNSIGNED NULL,

&#x20; state\_machine\_key VARCHAR(64) NOT NULL DEFAULT 'DEFAULT',

&#x20; sla\_config       JSON NULL,

&#x20; sort             INT NOT NULL DEFAULT 0,

&#x20; status           VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',

&#x20; created\_at       DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at       DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_type\_code (type\_code)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求类型字典';

CREATE TABLE demand (

&#x20; id                   BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_no            VARCHAR(40)  NOT NULL,

&#x20; title                VARCHAR(256) NOT NULL,

&#x20; demand\_type\_code     VARCHAR(32)  NOT NULL,

&#x20; subtype\_code         VARCHAR(32)  NULL,

&#x20; content              TEXT         NOT NULL,

&#x20; urgency              VARCHAR(16)  NOT NULL DEFAULT 'NORMAL',

&#x20; status               VARCHAR(32)  NOT NULL,

&#x20; on\_hold              TINYINT(1)   NOT NULL DEFAULT 0,

&#x20; hold\_reason          VARCHAR(256) NULL,

&#x20; hold\_snapshot\_status VARCHAR(32)  NULL,

&#x20; submitter\_id         BIGINT UNSIGNED NOT NULL,

&#x20; actual\_demander\_id   BIGINT UNSIGNED NULL,

&#x20; submitter\_org\_id     BIGINT UNSIGNED NULL,

&#x20; submitter\_org\_snapshot VARCHAR(256) NULL,

&#x20; channel              VARCHAR(32)  NULL,

&#x20; assignee\_org\_id      BIGINT UNSIGNED NULL,

&#x20; assignee\_user\_id     BIGINT UNSIGNED NULL,

&#x20; project\_id           BIGINT UNSIGNED NULL,

&#x20; expect\_delivery\_at   DATETIME(3)  NULL,

&#x20; actual\_delivery\_at   DATETIME(3)  NULL,

&#x20; submitted\_at         DATETIME(3)  NULL,

&#x20; closed\_at            DATETIME(3)  NULL,

&#x20; close\_reason         VARCHAR(256) NULL,

&#x20; quality\_score        TINYINT UNSIGNED NULL,

&#x20; satisfaction\_score   TINYINT UNSIGNED NULL,

&#x20; created\_at           DATETIME(3)  NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; created\_by           BIGINT UNSIGNED NOT NULL DEFAULT 0,

&#x20; updated\_at           DATETIME(3)  NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; updated\_by           BIGINT UNSIGNED NOT NULL DEFAULT 0,

&#x20; is\_deleted           TINYINT(1)   NOT NULL DEFAULT 0,

&#x20; version              INT          NOT NULL DEFAULT 0,

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_demand\_no (demand\_no),

&#x20; KEY idx\_status (status),

&#x20; KEY idx\_type\_status (demand\_type\_code, status),

&#x20; KEY idx\_submitter (submitter\_id),

&#x20; KEY idx\_assignee\_org (assignee\_org\_id, status),

&#x20; KEY idx\_assignee\_user (assignee\_user\_id, status),

&#x20; KEY idx\_project (project\_id),

&#x20; KEY idx\_submitted\_at (submitted\_at)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求基表';

CREATE TABLE demand\_ext\_tech (

&#x20; id                 BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id          BIGINT UNSIGNED NOT NULL,

&#x20; related\_system     VARCHAR(128) NULL,

&#x20; related\_module     VARCHAR(128) NULL,

&#x20; business\_scenario  TEXT NULL,

&#x20; acceptance\_criteria TEXT NULL,

&#x20; created\_at         DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at         DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_demand (demand\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='科技需求扩展';

CREATE TABLE demand\_ext\_material (

&#x20; id                 BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id          BIGINT UNSIGNED NOT NULL,

&#x20; material\_subtype   VARCHAR(64) NULL,

&#x20; usage\_scenario     VARCHAR(256) NULL,

&#x20; quantity           INT NULL,

&#x20; expected\_arrival\_at DATETIME(3) NULL,

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_demand (demand\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料需求扩展';

CREATE TABLE demand\_ext\_training (

&#x20; id                 BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id          BIGINT UNSIGNED NOT NULL,

&#x20; training\_subtype   VARCHAR(64) NULL,

&#x20; trainee\_object     VARCHAR(128) NULL,

&#x20; trainee\_count      INT NULL,

&#x20; expected\_complete\_at DATETIME(3) NULL,

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_demand (demand\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='培训需求扩展';

CREATE TABLE demand\_relation (

&#x20; id                 BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id          BIGINT UNSIGNED NOT NULL,

&#x20; related\_demand\_id  BIGINT UNSIGNED NOT NULL,

&#x20; relation\_type      VARCHAR(16) NOT NULL,

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_pair (demand\_id, related\_demand\_id, relation\_type),

&#x20; KEY idx\_related (related\_demand\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求关联';

CREATE TABLE demand\_draft (

&#x20; id                  BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; user\_id             BIGINT UNSIGNED NOT NULL,

&#x20; channel             VARCHAR(32) NULL,

&#x20; conversation        JSON NULL,

&#x20; voice\_transcript    TEXT NULL,

&#x20; form\_payload        JSON NULL,

&#x20; converted\_demand\_id BIGINT UNSIGNED NULL,

&#x20; created\_at          DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at          DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_converted (converted\_demand\_id),

&#x20; KEY idx\_user (user\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求草稿';

CREATE TABLE attachment (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; biz\_type      VARCHAR(32) NOT NULL,

&#x20; biz\_id        BIGINT UNSIGNED NOT NULL,

&#x20; file\_name     VARCHAR(256) NOT NULL,

&#x20; file\_path     VARCHAR(512) NOT NULL,

&#x20; file\_size     BIGINT UNSIGNED NOT NULL DEFAULT 0,

&#x20; mime\_type     VARCHAR(128) NULL,

&#x20; ext           VARCHAR(16) NULL,

&#x20; transcript    TEXT NULL,

&#x20; uploaded\_by   BIGINT UNSIGNED NOT NULL,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_biz (biz\_type, biz\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='附件';

\-- ---------- 处理与流转域 ----------

CREATE TABLE assignment (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id     BIGINT UNSIGNED NOT NULL,

&#x20; org\_id        BIGINT UNSIGNED NOT NULL,

&#x20; assignee\_id   BIGINT UNSIGNED NULL,

&#x20; dispatcher\_id BIGINT UNSIGNED NULL,

&#x20; assign\_mode   VARCHAR(16) NOT NULL COMMENT 'DISPATCH/CLAIM',

&#x20; status        VARCHAR(16) NOT NULL DEFAULT 'OPEN',

&#x20; assigned\_at   DATETIME(3) NULL,

&#x20; claimed\_at    DATETIME(3) NULL,

&#x20; finished\_at   DATETIME(3) NULL,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_demand (demand\_id),

&#x20; KEY idx\_org\_status (org\_id, status),

&#x20; KEY idx\_assignee (assignee\_id, status)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='处理任务分派';

CREATE TABLE demand\_transition\_log (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id     BIGINT UNSIGNED NOT NULL,

&#x20; from\_status   VARCHAR(32) NULL,

&#x20; to\_status     VARCHAR(32) NOT NULL,

&#x20; action        VARCHAR(64) NOT NULL,

&#x20; operator\_id   BIGINT UNSIGNED NOT NULL,

&#x20; operator\_snapshot VARCHAR(128) NULL,

&#x20; comment       TEXT NULL,

&#x20; extra         JSON NULL,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_demand\_time (demand\_id, created\_at)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求流转日志';

CREATE TABLE solution (

&#x20; id                BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id         BIGINT UNSIGNED NOT NULL,

&#x20; version           INT NOT NULL,

&#x20; author\_id         BIGINT UNSIGNED NOT NULL,

&#x20; spec\_content      TEXT NULL,

&#x20; solution\_content  TEXT NULL,

&#x20; plan\_delivery\_at  DATETIME(3) NULL,

&#x20; actual\_delivery\_at DATETIME(3) NULL,

&#x20; status            VARCHAR(16) NOT NULL DEFAULT 'DRAFT',

&#x20; remark            VARCHAR(512) NULL,

&#x20; created\_at        DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at        DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_demand\_version (demand\_id, version)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求方案';

CREATE TABLE review (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id     BIGINT UNSIGNED NOT NULL,

&#x20; solution\_id   BIGINT UNSIGNED NULL,

&#x20; review\_type   VARCHAR(16) NOT NULL COMMENT 'SOLUTION/ACCEPTANCE',

&#x20; reviewer\_id   BIGINT UNSIGNED NOT NULL,

&#x20; conclusion    VARCHAR(16) NOT NULL COMMENT 'PASS/REJECT',

&#x20; quality\_score TINYINT UNSIGNED NULL,

&#x20; comment       TEXT NULL,

&#x20; reviewed\_at   DATETIME(3) NOT NULL,

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_demand\_type (demand\_id, review\_type)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='评审/验收';

CREATE TABLE effort\_log (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id     BIGINT UNSIGNED NOT NULL,

&#x20; user\_id       BIGINT UNSIGNED NOT NULL,

&#x20; hours         DECIMAL(5,1) NOT NULL DEFAULT 0,

&#x20; work\_date     DATE NOT NULL,

&#x20; description   VARCHAR(512) NULL,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_demand (demand\_id),

&#x20; KEY idx\_user\_date (user\_id, work\_date)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工时记录';

CREATE TABLE comment (

&#x20; id                BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id         BIGINT UNSIGNED NOT NULL,

&#x20; author\_id         BIGINT UNSIGNED NOT NULL,

&#x20; content           TEXT NOT NULL,

&#x20; mentioned\_user\_ids VARCHAR(512) NULL,

&#x20; created\_at        DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_demand\_time (demand\_id, created\_at)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求评论';

\-- ---------- 项目域 ----------

CREATE TABLE project (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; name          VARCHAR(256) NOT NULL,

&#x20; owner\_id      BIGINT UNSIGNED NULL,

&#x20; status        VARCHAR(16) NOT NULL DEFAULT 'PLANNING',

&#x20; started\_at    DATETIME(3) NULL,

&#x20; ended\_at      DATETIME(3) NULL,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; is\_deleted    TINYINT(1) NOT NULL DEFAULT 0,

&#x20; version       INT NOT NULL DEFAULT 0,

&#x20; PRIMARY KEY (id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目';

CREATE TABLE project\_milestone (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; project\_id    BIGINT UNSIGNED NOT NULL,

&#x20; name          VARCHAR(128) NOT NULL,

&#x20; plan\_at       DATETIME(3) NULL,

&#x20; actual\_at     DATETIME(3) NULL,

&#x20; status        VARCHAR(16) NOT NULL DEFAULT 'PLANNED',

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_project (project\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目里程碑';

\-- ---------- 通知域 ----------

CREATE TABLE notification (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; demand\_id     BIGINT UNSIGNED NULL,

&#x20; receiver\_id   BIGINT UNSIGNED NOT NULL,

&#x20; channel       VARCHAR(16) NOT NULL DEFAULT 'IN\_APP',

&#x20; template\_code VARCHAR(64) NULL,

&#x20; title         VARCHAR(256) NOT NULL,

&#x20; content       TEXT NULL,

&#x20; link          VARCHAR(512) NULL,

&#x20; is\_read       TINYINT(1) NOT NULL DEFAULT 0,

&#x20; read\_at       DATETIME(3) NULL,

&#x20; send\_status   VARCHAR(16) NOT NULL DEFAULT 'PENDING',

&#x20; retry\_count   INT NOT NULL DEFAULT 0,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; sent\_at       DATETIME(3) NULL,

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_receiver\_unread (receiver\_id, is\_read),

&#x20; KEY idx\_demand (demand\_id)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通知消息';

\-- ---------- 支撑表 ----------

CREATE TABLE agent\_session (

&#x20; id            BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; user\_id       BIGINT UNSIGNED NOT NULL,

&#x20; scene         VARCHAR(32) NOT NULL,

&#x20; demand\_id     BIGINT UNSIGNED NULL,

&#x20; trace\_id      VARCHAR(64) NULL,

&#x20; messages      JSON NULL,

&#x20; created\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3),

&#x20; updated\_at    DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; KEY idx\_user\_scene (user\_id, scene)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 会话';

CREATE TABLE demand\_stat\_daily (

&#x20; id                 BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; stat\_date          DATE NOT NULL,

&#x20; demand\_type\_code   VARCHAR(32) NOT NULL,

&#x20; assignee\_org\_id    BIGINT UNSIGNED NOT NULL DEFAULT 0,

&#x20; reporter\_org\_id    BIGINT UNSIGNED NOT NULL DEFAULT 0,

&#x20; status             VARCHAR(32) NOT NULL,

&#x20; cnt                INT NOT NULL DEFAULT 0,

&#x20; avg\_cycle\_hours    DECIMAL(10,2) NULL,

&#x20; updated\_at         DATETIME(3) NOT NULL DEFAULT CURRENT\_TIMESTAMP(3) ON UPDATE CURRENT\_TIMESTAMP(3),

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_dim (stat\_date, demand\_type\_code, assignee\_org\_id, reporter\_org\_id, status)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求日统计预聚合';

CREATE TABLE sys\_dict (

&#x20; id           BIGINT UNSIGNED NOT NULL AUTO\_INCREMENT,

&#x20; dict\_type    VARCHAR(64) NOT NULL,

&#x20; item\_code    VARCHAR(64) NOT NULL,

&#x20; item\_name    VARCHAR(128) NOT NULL,

&#x20; sort         INT NOT NULL DEFAULT 0,

&#x20; status       VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',

&#x20; PRIMARY KEY (id),

&#x20; UNIQUE KEY uk\_type\_code (dict\_type, item\_code)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通用字典';

SET FOREIGN\_KEY\_CHECKS = 1;
```



***

## 5. 初始化数据

### 5.1 业务角色授权说明

> 业务角色编码已在 demand_role_grant.role_code 中固定（ADMIN / EXECUTIVE / TECH_MANAGER / MATL_MANAGER / TRAIN_MANAGER / TECH_HANDLER / MATL_HANDLER / TRAIN_HANDLER），无需独立角色表。授权由系统管理员在 DemandHub 后台操作，非初始化数据。示例：

\-- INSERT INTO demand_role_grant(demand_user_id, role_code, org_id, granted_by) VALUES
--   ('u_admin_001', 'ADMIN',        NULL, 'u_admin_001'),
--   ('u_exec_001',   'EXECUTIVE',     NULL, 'u_admin_001'),
--   ('u_mgr_tech',   'DEMAND_MANAGER', 128, 'u_admin_001'),
--   ('u_handler_1', 'HANDLER',       128, 'u_mgr_tech'),
--   ('u_reporter_1','REPORTER',      NULL, 'u_admin_001');
\
### 5.2 需求类型初始化



```
INSERT INTO demand\_type(type\_code, type\_name, default\_org\_id, state\_machine\_key, sort) VALUES

('TECH',   '科技需求',  /\* 财管科技产品部 org\_id \*/ NULL, 'DEFAULT', 1),

('MATL',   '物料需求',  /\* 客户陪伴服务部 org\_id \*/ NULL, 'DEFAULT', 2),

('TRAIN',  '培训需求',  /\* 培训开发部 org\_id \*/     NULL, 'DEFAULT', 3);
```

### 5.3 字典初始化



```
INSERT INTO sys\_dict(dict\_type, item\_code, item\_name, sort) VALUES

('URGENCY','NORMAL',  '普通', 1),

('URGENCY','URGENT',  '紧急', 2),

('URGENCY','CRITICAL','特急', 3),

('CLOSE\_REASON','NOT\_ACCEPTED','不受理',1),

('CLOSE\_REASON','DUPLICATE',   '重复需求',2),

('CLOSE\_REASON','REVOKED',     '提报人撤销',3),

('HOLD\_REASON','WAIT\_EXTERNAL','等待外部依赖',1),

('HOLD\_REASON','WAIT\_RESOURCE','等待资源',2),

('HOLD\_REASON','OTHER',        '其他',9);
```



***

## 6. 索引与查询策略



| 场景      | 主查询                                                              | 命中索引                    |
| ------- | ---------------------------------------------------------------- | ----------------------- |
| 经理待受理   | `assignee_org_id=? AND status='SUBMITTED' ORDER BY submitted_at` | `idx_assignee_org`      |
| 我的待办    | `assignee_user_id=? AND status IN (...) `                        | `idx_assignee_user`     |
| 提报人我的需求 | `submitter_id=? ORDER BY created_at DESC`                        | `idx_submitter`         |
| 管理者看板   | 按 type/org/status 汇总                                             | `demand_stat_daily` 预聚合 |
| 子树组织查询  | `path LIKE '/1/15/%'`                                            | `idx_path`              |
| 详情时间线   | `demand_id=? ORDER BY created_at`                                | `idx_demand_time`       |



***

## 7. 数据迁移与演进



* 一期无历史数据迁移；二期对接外部系统时，以 `demand_no` 为业务键做幂等导入。

* 新增需求类型：在 `demand_type` 插记录 + 建对应扩展表 + 配置状态机，不改核心表。

* 组织调整：管理员在 DemandHub 后台调整 `demand_org` 树（拆分/合并），不影响 `demand.submitter_org_snapshot` 历史快照。

* 归档：超过 3 年的已完成 / 已关闭需求可归档到历史库，主库仅保留热数据。



***

## 8. 版本记录



| 版本   | 日期         | 变更 | 作者      |
| ---- | ---------- | -- | ------- |
| v1.0 | 2026-09-19 | 初稿 | 财管科技产品部 |
| v1.1 | 2026-09-19 | 按评审意见修订：删除自建 sys_user/sys_org_unit/sys_user_org_rel/sys_role/sys_permission/sys_role_permission/sys_user_role_grant 七张主表，改为 demand_user_snapshot / demand_org_snapshot 两张只读镜像表 + demand_role_grant 业务角色本地授权表；ER 图、DDL、初始化数据、演进章节同步 | 财管科技产品部 
| v1.2 | 2026-09-22 | 用户/权限模块重构：DemandHub 改为自有 OneID 用户体系与可维护组织树；新增 demand_channel 渠道注册表与 channel_user_mapping 渠道用户映射表；业务角色按需求类型细分（TECH/MATL/TRAIN × MANAGER/HANDLER），去掉 REPORTER；新用户待完善与用户合并流程 | 财管科技产品部 ||
| v1.3 | 2026-09-22 | 嵌入方案定稿为创金零售 SSO 票据：渠道枚举去 WECOM_APP（预留 DISABLED）、一期启用 CHUANGJIN_LS；demand_user 增 login_name/password_hash/password_updated_at（PC 账密）；demand_org 增 external_dept_id；config_json 改存 SSO 校验配置；角色码注释改为角色族；票据有效用户自动 ACTIVE 建号 | 财管科技产品部 ||
| v1.4 | 2026-09-22 | 冻结 verify 字段口径：wecom_userid 为必填首选匹配键、手机号选填辅助；匹配优先级改为企微 userid > 手机号（3.1.1/3.1.2） | 财管科技产品部 ||
