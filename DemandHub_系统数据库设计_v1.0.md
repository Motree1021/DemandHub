# DemandHub 零售业务线需求管理系统・系统数据库设计

| 项目   | 内容                                    |
| ---- | ------------------------------------- |
| 文档名称 | DemandHub 系统数据库设计                     |
| 版本   | v1.1                                  |
| DBMS | MySQL 8.0（InnoDB，utf8mb4）             |
| 编制部门 | 财管科技产品部                               |
| 编制日期 | 2026-09-19                            |
| 上游文档 | 概念模型 v0.2、BRD v1.1、SRS v1.1、架构设计 v1.1 |



***

## 1. 设计约定



1. **主键**：统一 `BIGINT UNSIGNED` 自增主键 `id`，业务编号单独字段（如 `demand_no`）并建唯一索引。

2. **公共字段**：所有业务表含 `created_at / created_by / updated_at / updated_by / is_deleted / version`。

3. **软删除**：`is_deleted TINYINT(1) DEFAULT 0`，查询默认过滤。

4. **时间**：`DATETIME(3)`，时区统一 Asia/Shanghai，应用层写入。

5. **金额 / 数量**：本系统无金额；数量类用 `INT`，工时用 `DECIMAL(5,1)`。

6. **组织树**：`demand_org_snapshot` 用 `parent_id` 自关联 + `path` 物化路径（如 `/1/15/128/`）便于子树查询；该表为零售统一权限中心的只读镜像，本地不提供增删改界面。

7. **状态 / 类型**：用 `VARCHAR(32)` 存枚举码，字典表维护中文名，不使用 MySQL ENUM（便于扩展）。

8. **扩展表**：需求基表 `demand` + 类型扩展表（`demand_ext_tech/material/training`），共享主键 `demand_id`（1:1）。

9. **索引**：外键字段必建索引；高频查询组合字段建联合索引；不建过度索引。

10. **审计**：流转日志、评论、通知只增不改。



***

## 2. ER 总览（实体关系）



```
【主数据：零售统一权限中心 → DemandHub 只读镜像】
demand_user_snapshot ──> demand_org_snapshot（经 primary_org_id 关联）

【业务角色：DemandHub 本地维护】
demand_role_grant（user_id × role_code × org_id × type_scope）

demand_user_snapshot ─┬─< demand (提报人/代办人/处理人/操作人)
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

> 设计边界：用户/组织主数据不在 DemandHub 本地建表维护，由零售统一权限中心每日全量 + 每 5 分钟增量同步到只读镜像；本地仅维护业务角色授权 `demand_role_grant`。



***

## 3. 表结构详细设计

### 3.1 主数据与业务角色域

> **设计原则**：身份与组织主数据来自零售业务线统一权限中心（与"创金零售"同源），DemandHub 本地仅存**只读镜像**；业务角色授权（需求经理/处理人等）属业务域，在 DemandHub 本地表维护。本域不提供用户/组织的增删改管理界面。

#### 3.1.1 `demand_user_snapshot` 用户只读镜像表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INC | 本地主键 |
| user_id | VARCHAR(64) | UNIQUE | 权限中心用户唯一 ID |
| name | VARCHAR(64) | NOT NULL | 姓名 |
| wecom_id | VARCHAR(64) | UNIQUE | 企微 userid |
| employee_no | VARCHAR(32) | | 工号 |
| primary_org_id | BIGINT UNSIGNED | | 主组织，关联 demand_org_snapshot.org_id |
| dept_path | VARCHAR(512) | | 部门路径快照，如 `/零售线/财管科技产品部/产品组` |
| phone | VARCHAR(32) | | 手机号（脱敏存储） |
| email | VARCHAR(128) | | 邮箱 |
| status | VARCHAR(16) | NOT NULL DEFAULT 'ACTIVE' | ACTIVE / DISABLED |
| synced_at | DATETIME(3) | | 最近一次同步时间 |
| created_at / updated_at | | | |

索引：`uk_user_id(user_id)`、`uk_wecom_id(wecom_id)`、`idx_primary_org(primary_org_id)`、`idx_status(status)`。

> 本表由同步任务每日全量 + 每 5 分钟增量写入，业务代码只读；不做软删除，权限中心停用即置 status=DISABLED。

#### 3.1.2 `demand_org_snapshot` 组织节点只读镜像表

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | BIGINT UNSIGNED | PK, AUTO_INC | 本地主键 |
| org_id | BIGINT UNSIGNED | UNIQUE | 权限中心组织节点 ID |
| name | VARCHAR(128) | NOT NULL | 组织名称 |
| level | VARCHAR(16) | NOT NULL | LINE / DEPT / GROUP |
| parent_id | BIGINT UNSIGNED | NOT NULL DEFAULT 0 | 父节点（引用本表 org_id 口径），根 = 0 |
| path | VARCHAR(512) | NOT NULL | 物化路径，如 `/1/15/128/` |
| org_kind | VARCHAR(16) | | REPORTER / ASSIGNER / BOTH |
| status | VARCHAR(16) | NOT NULL DEFAULT 'ACTIVE' | ACTIVE / DISABLED |
| synced_at | DATETIME(3) | | 最近一次同步时间 |

索引：`uk_org_id(org_id)`、`idx_parent(parent_id)`、`idx_path(path)`、`idx_status(status)`。

> 本表为权限中心组织树镜像；DemandHub 不提供组织节点增删改界面。组织拆分/合并由权限中心负责，镜像自动跟随。

#### 3.1.3 `demand_role_grant` 业务角色授权表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT UNSIGNED PK | |
| user_id | VARCHAR(64) NOT NULL | 引用 demand_user_snapshot.user_id |
| role_code | VARCHAR(32) NOT NULL | ADMIN / EXECUTIVE / DEMAND_MANAGER / HANDLER / REPORTER |
| org_id | BIGINT UNSIGNED NULL | 授权组织范围（引用 demand_org_snapshot.org_id，空 = 不限） |
| demand_type_scope | VARCHAR(256) | 覆盖类型范围，逗号分隔；空 = 跟随角色默认 |
| effective_from | DATETIME(3) | 生效起 |
| effective_to | DATETIME(3) NULL | 生效止 |
| granted_by | VARCHAR(64) | 授予人（user_id） |
| created_at / updated_at | | |

索引：`uk_grant(user_id, role_code, org_id, demand_type_scope, is_deleted)`、`idx_org(org_id)`、`idx_role(role_code)`。

> 业务角色编码固定为：ADMIN（系统管理员）、EXECUTIVE（需求管理者）、DEMAND_MANAGER（需求经理）、HANDLER（需求处理人员）、REPORTER（需求提报人）。一个用户可拥有多条授权。



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
| channel                                                                       | VARCHAR(32)                            | WEB / WECOM\_H5 / WECOM\_BOT / VOICE                                                                       |
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

\-- ---------- 主数据镜像与业务角色（零售统一权限中心同步） ----------

CREATE TABLE demand_user_snapshot (

  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

  user_id         VARCHAR(64)  NOT NULL COMMENT '权限中心用户唯一ID',

  name            VARCHAR(64)  NOT NULL,

  wecom_id        VARCHAR(64)  NULL,

  employee_no     VARCHAR(32)  NULL,

  primary_org_id  BIGINT UNSIGNED NULL,

  dept_path       VARCHAR(512) NULL,

  phone           VARCHAR(32)  NULL,

  email           VARCHAR(128) NULL,

  status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',

  synced_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),

  UNIQUE KEY uk_user_id (user_id),

  UNIQUE KEY uk_wecom_id (wecom_id),

  KEY idx_primary_org (primary_org_id),

  KEY idx_status (status)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户只读镜像（权限中心同步）';

CREATE TABLE demand_org_snapshot (

  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

  org_id          BIGINT UNSIGNED NOT NULL,

  name            VARCHAR(128) NOT NULL,

  level           VARCHAR(16)  NOT NULL COMMENT 'LINE/DEPT/GROUP',

  parent_id       BIGINT UNSIGNED NOT NULL DEFAULT 0,

  path            VARCHAR(512) NOT NULL,

  org_kind        VARCHAR(16)  NULL COMMENT 'REPORTER/ASSIGNER/BOTH',

  status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',

  synced_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),

  UNIQUE KEY uk_org_id (org_id),

  KEY idx_parent (parent_id),

  KEY idx_path (path),

  KEY idx_status (status)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='组织节点只读镜像（权限中心同步）';

CREATE TABLE demand_role_grant (

  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,

  user_id             VARCHAR(64)  NOT NULL,

  role_code           VARCHAR(32)  NOT NULL COMMENT 'ADMIN/EXECUTIVE/DEMAND_MANAGER/HANDLER/REPORTER',

  org_id              BIGINT UNSIGNED NULL,

  demand_type_scope   VARCHAR(256) NULL,

  effective_from      DATETIME(3) NULL,

  effective_to        DATETIME(3) NULL,

  granted_by          VARCHAR(64) NULL,

  is_deleted          TINYINT(1)  NOT NULL DEFAULT 0,

  created_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),

  updated_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),

  PRIMARY KEY (id),

  UNIQUE KEY uk_grant (user_id, role_code, org_id, demand_type_scope, is_deleted),

  KEY idx_org (org_id),

  KEY idx_role (role_code)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务角色本地授权';

\-- ---------- 需求域 ----------

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

> 业务角色编码已在 demand_role_grant.role_code 中固定（ADMIN / EXECUTIVE / DEMAND_MANAGER / HANDLER / REPORTER），无需独立角色表。授权由系统管理员在 DemandHub 后台操作，非初始化数据。示例：

\-- INSERT INTO demand_role_grant(user_id, role_code, org_id, granted_by) VALUES
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

* 组织调整：`demand_org_snapshot` 跟随权限中心自动同步，不影响 `demand.submitter_org_snapshot` 历史快照。

* 归档：超过 3 年的已完成 / 已关闭需求可归档到历史库，主库仅保留热数据。



***

## 8. 版本记录



| 版本   | 日期         | 变更 | 作者      |
| ---- | ---------- | -- | ------- |
| v1.0 | 2026-09-19 | 初稿 | 财管科技产品部 |
| v1.1 | 2026-09-19 | 按评审意见修订：删除自建 sys_user/sys_org_unit/sys_user_org_rel/sys_role/sys_permission/sys_role_permission/sys_user_role_grant 七张主表，改为 demand_user_snapshot / demand_org_snapshot 两张只读镜像表 + demand_role_grant 业务角色本地授权表；ER 图、DDL、初始化数据、演进章节同步 | 财管科技产品部 |