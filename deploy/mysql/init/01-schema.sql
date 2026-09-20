-- =========================================================
-- DemandHub DDL v1.1  MySQL 8.0  InnoDB  utf8mb4_0900_ai_ci
-- 来源：DemandHub_系统数据库设计_v1.1 第 4 节
-- =========================================================

CREATE DATABASE IF NOT EXISTS demandhub DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE demandhub;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------- 主数据镜像与业务角色（零售统一权限中心同步） ----------

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

-- ---------- 需求域 ----------

CREATE TABLE demand_type (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  type_code        VARCHAR(32) NOT NULL,
  type_name        VARCHAR(64) NOT NULL,
  parent_type_code VARCHAR(32) NULL,
  default_org_id   BIGINT UNSIGNED NULL,
  state_machine_key VARCHAR(64) NOT NULL DEFAULT 'DEFAULT',
  sla_config       JSON NULL,
  sort             INT NOT NULL DEFAULT 0,
  status           VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_type_code (type_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求类型字典';

CREATE TABLE demand (
  id                   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_no            VARCHAR(40)  NOT NULL,
  title                VARCHAR(256) NOT NULL,
  demand_type_code     VARCHAR(32)  NOT NULL,
  subtype_code         VARCHAR(32)  NULL,
  content              TEXT         NOT NULL,
  urgency              VARCHAR(16)  NOT NULL DEFAULT 'NORMAL',
  status               VARCHAR(32)  NOT NULL,
  on_hold              TINYINT(1)   NOT NULL DEFAULT 0,
  hold_reason          VARCHAR(256) NULL,
  hold_snapshot_status VARCHAR(32)  NULL,
  submitter_id         BIGINT UNSIGNED NOT NULL,
  actual_demander_id   BIGINT UNSIGNED NULL,
  submitter_org_id     BIGINT UNSIGNED NULL,
  submitter_org_snapshot VARCHAR(256) NULL,
  channel              VARCHAR(32)  NULL,
  assignee_org_id      BIGINT UNSIGNED NULL,
  assignee_user_id     BIGINT UNSIGNED NULL,
  project_id           BIGINT UNSIGNED NULL,
  expect_delivery_at   DATETIME(3)  NULL,
  actual_delivery_at   DATETIME(3)  NULL,
  submitted_at         DATETIME(3)  NULL,
  closed_at            DATETIME(3)  NULL,
  close_reason         VARCHAR(256) NULL,
  quality_score        TINYINT UNSIGNED NULL,
  satisfaction_score   TINYINT UNSIGNED NULL,
  created_at           DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  created_by           BIGINT UNSIGNED NOT NULL DEFAULT 0,
  updated_at           DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  updated_by           BIGINT UNSIGNED NOT NULL DEFAULT 0,
  is_deleted           TINYINT(1)   NOT NULL DEFAULT 0,
  version              INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uk_demand_no (demand_no),
  KEY idx_status (status),
  KEY idx_type_status (demand_type_code, status),
  KEY idx_submitter (submitter_id),
  KEY idx_assignee_org (assignee_org_id, status),
  KEY idx_assignee_user (assignee_user_id, status),
  KEY idx_project (project_id),
  KEY idx_submitted_at (submitted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求基表';

CREATE TABLE demand_ext_tech (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id          BIGINT UNSIGNED NOT NULL,
  related_system     VARCHAR(128) NULL,
  related_module     VARCHAR(128) NULL,
  business_scenario  TEXT NULL,
  acceptance_criteria TEXT NULL,
  created_at         DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at         DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_demand (demand_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='科技需求扩展';

CREATE TABLE demand_ext_material (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id          BIGINT UNSIGNED NOT NULL,
  material_subtype   VARCHAR(64) NULL,
  usage_scenario     VARCHAR(256) NULL,
  quantity           INT NULL,
  expected_arrival_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_demand (demand_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='物料需求扩展';

CREATE TABLE demand_ext_training (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id          BIGINT UNSIGNED NOT NULL,
  training_subtype   VARCHAR(64) NULL,
  trainee_object     VARCHAR(128) NULL,
  trainee_count      INT NULL,
  expected_complete_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_demand (demand_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='培训需求扩展';

CREATE TABLE demand_relation (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id          BIGINT UNSIGNED NOT NULL,
  related_demand_id  BIGINT UNSIGNED NOT NULL,
  relation_type      VARCHAR(16) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_pair (demand_id, related_demand_id, relation_type),
  KEY idx_related (related_demand_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求关联';

CREATE TABLE demand_draft (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id             BIGINT UNSIGNED NOT NULL,
  channel             VARCHAR(32) NULL,
  conversation        JSON NULL,
  voice_transcript    TEXT NULL,
  form_payload        JSON NULL,
  converted_demand_id BIGINT UNSIGNED NULL,
  created_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_converted (converted_demand_id),
  KEY idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求草稿';

CREATE TABLE attachment (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  biz_type      VARCHAR(32) NOT NULL,
  biz_id        BIGINT UNSIGNED NOT NULL,
  file_name     VARCHAR(256) NOT NULL,
  file_path     VARCHAR(512) NOT NULL,
  file_size     BIGINT UNSIGNED NOT NULL DEFAULT 0,
  mime_type     VARCHAR(128) NULL,
  ext           VARCHAR(16) NULL,
  transcript    TEXT NULL,
  uploaded_by   BIGINT UNSIGNED NOT NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_biz (biz_type, biz_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='附件';

-- ---------- 处理与流转域 ----------

CREATE TABLE assignment (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id     BIGINT UNSIGNED NOT NULL,
  org_id        BIGINT UNSIGNED NOT NULL,
  assignee_id   BIGINT UNSIGNED NULL,
  dispatcher_id BIGINT UNSIGNED NULL,
  assign_mode   VARCHAR(16) NOT NULL COMMENT 'DISPATCH/CLAIM',
  status        VARCHAR(16) NOT NULL DEFAULT 'OPEN',
  assigned_at   DATETIME(3) NULL,
  claimed_at    DATETIME(3) NULL,
  finished_at   DATETIME(3) NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_demand (demand_id),
  KEY idx_org_status (org_id, status),
  KEY idx_assignee (assignee_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='处理任务分派';

CREATE TABLE demand_transition_log (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id     BIGINT UNSIGNED NOT NULL,
  from_status   VARCHAR(32) NULL,
  to_status     VARCHAR(32) NOT NULL,
  action        VARCHAR(64) NOT NULL,
  operator_id   BIGINT UNSIGNED NOT NULL,
  operator_snapshot VARCHAR(128) NULL,
  comment       TEXT NULL,
  extra         JSON NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_demand_time (demand_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求流转日志';

CREATE TABLE solution (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id         BIGINT UNSIGNED NOT NULL,
  version           INT NOT NULL,
  author_id         BIGINT UNSIGNED NOT NULL,
  spec_content      TEXT NULL,
  solution_content  TEXT NULL,
  plan_delivery_at  DATETIME(3) NULL,
  actual_delivery_at DATETIME(3) NULL,
  status            VARCHAR(16) NOT NULL DEFAULT 'DRAFT',
  remark            VARCHAR(512) NULL,
  created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_demand_version (demand_id, version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求方案';

CREATE TABLE review (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id     BIGINT UNSIGNED NOT NULL,
  solution_id   BIGINT UNSIGNED NULL,
  review_type   VARCHAR(16) NOT NULL COMMENT 'SOLUTION/ACCEPTANCE',
  reviewer_id   BIGINT UNSIGNED NOT NULL,
  conclusion    VARCHAR(16) NOT NULL COMMENT 'PASS/REJECT',
  quality_score TINYINT UNSIGNED NULL,
  comment       TEXT NULL,
  reviewed_at   DATETIME(3) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_demand_type (demand_id, review_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='评审/验收';

CREATE TABLE effort_log (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id     BIGINT UNSIGNED NOT NULL,
  user_id       BIGINT UNSIGNED NOT NULL,
  hours         DECIMAL(5,1) NOT NULL DEFAULT 0,
  work_date     DATE NOT NULL,
  description   VARCHAR(512) NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_demand (demand_id),
  KEY idx_user_date (user_id, work_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='工时记录';

CREATE TABLE comment (
  id                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id         BIGINT UNSIGNED NOT NULL,
  author_id         BIGINT UNSIGNED NOT NULL,
  content           TEXT NOT NULL,
  mentioned_user_ids VARCHAR(512) NULL,
  created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_demand_time (demand_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求评论';

-- ---------- 项目域 ----------

CREATE TABLE project (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name          VARCHAR(256) NOT NULL,
  owner_id      BIGINT UNSIGNED NULL,
  status        VARCHAR(16) NOT NULL DEFAULT 'PLANNING',
  started_at    DATETIME(3) NULL,
  ended_at      DATETIME(3) NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  is_deleted    TINYINT(1) NOT NULL DEFAULT 0,
  version       INT NOT NULL DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目';

CREATE TABLE project_milestone (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  project_id    BIGINT UNSIGNED NOT NULL,
  name          VARCHAR(128) NOT NULL,
  plan_at       DATETIME(3) NULL,
  actual_at     DATETIME(3) NULL,
  status        VARCHAR(16) NOT NULL DEFAULT 'PLANNED',
  PRIMARY KEY (id),
  KEY idx_project (project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目里程碑';

-- ---------- 通知域 ----------

CREATE TABLE notification (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id     BIGINT UNSIGNED NULL,
  receiver_id   BIGINT UNSIGNED NOT NULL,
  channel       VARCHAR(16) NOT NULL DEFAULT 'IN_APP',
  template_code VARCHAR(64) NULL,
  title         VARCHAR(256) NOT NULL,
  content       TEXT NULL,
  link          VARCHAR(512) NULL,
  is_read       TINYINT(1) NOT NULL DEFAULT 0,
  read_at       DATETIME(3) NULL,
  send_status   VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  retry_count   INT NOT NULL DEFAULT 0,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  sent_at       DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_receiver_unread (receiver_id, is_read),
  KEY idx_demand (demand_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通知消息';

-- ---------- 支撑表 ----------

CREATE TABLE agent_session (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id       BIGINT UNSIGNED NOT NULL,
  scene         VARCHAR(32) NOT NULL,
  demand_id     BIGINT UNSIGNED NULL,
  trace_id      VARCHAR(64) NULL,
  messages      JSON NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_user_scene (user_id, scene)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 会话';

CREATE TABLE demand_stat_daily (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  stat_date          DATE NOT NULL,
  demand_type_code   VARCHAR(32) NOT NULL,
  assignee_org_id    BIGINT UNSIGNED NOT NULL DEFAULT 0,
  reporter_org_id    BIGINT UNSIGNED NOT NULL DEFAULT 0,
  status             VARCHAR(32) NOT NULL,
  cnt                INT NOT NULL DEFAULT 0,
  avg_cycle_hours    DECIMAL(10,2) NULL,
  updated_at         DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_dim (stat_date, demand_type_code, assignee_org_id, reporter_org_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求日统计预聚合';

CREATE TABLE sys_dict (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  dict_type    VARCHAR(64) NOT NULL,
  item_code    VARCHAR(64) NOT NULL,
  item_name    VARCHAR(128) NOT NULL,
  sort         INT NOT NULL DEFAULT 0,
  status       VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
  PRIMARY KEY (id),
  UNIQUE KEY uk_type_code (dict_type, item_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通用字典';

SET FOREIGN_KEY_CHECKS = 1;
