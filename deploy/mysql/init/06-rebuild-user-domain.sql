-- =========================================================
-- DemandHub 用户域重建与迁移（鉴权重构 P1）
-- 来源：开发计划 v2.0 任务 1.1/1.2、库设计 v1.3 第 3.1 节
-- 适用两套路径：
--   A. 旧库（已建 demand_user_snapshot / demand_org_snapshot / 旧 demand_role_grant）：
--      旧表改名 *_legacy 保留一迭代（回滚用），随后建新表并写入种子。
--   B. 全新库：01-schema.sql 已建新表，本脚本 CREATE IF NOT EXISTS 为 no-op，种子幂等补齐。
-- 执行：docker exec -i demandhub-mysql mysql -uroot -pdemandhub123 demandhub < deploy/mysql/init/06-rebuild-user-domain.sql
-- 回滚：deploy/mysql/06-rollback.sql（手工执行，刻意不放在 init/ 避免全新初始化被自动跑）
-- =========================================================

SET NAMES utf8mb4;
USE demandhub;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------- 1) 旧表改名保留（存在才改名；重复执行本脚本先清掉上一轮 legacy） ----------
DROP TABLE IF EXISTS demand_user_snapshot_legacy;
DROP TABLE IF EXISTS demand_org_snapshot_legacy;
DROP TABLE IF EXISTS demand_role_grant_legacy;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_user_snapshot') > 0,
               'RENAME TABLE demand_user_snapshot TO demand_user_snapshot_legacy', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := IF((SELECT COUNT(*) FROM information_schema.TABLES
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_org_snapshot') > 0,
               'RENAME TABLE demand_org_snapshot TO demand_org_snapshot_legacy', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 旧 demand_role_grant 为 user_id VARCHAR 结构，与新结构不兼容，改名保留
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_role_grant' AND COLUMN_NAME='user_id') > 0,
               'RENAME TABLE demand_role_grant TO demand_role_grant_legacy', 'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- 2) 新五表（与 01-schema.sql v1.3 一致，IF NOT EXISTS 保证全新库 no-op） ----------

CREATE TABLE IF NOT EXISTS demand_channel (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  channel_code    VARCHAR(32)  NOT NULL COMMENT 'WEB/CHUANGJIN_LS/WECOM_BOT/FEISHU_BOT/DOUBAO_WORK/WORKBUDDY/VOICE（WECOM_APP预留，一期DISABLED）',
  channel_name    VARCHAR(64)  NOT NULL,
  app_id          VARCHAR(128) NULL COMMENT '渠道侧应用ID（创金零售SSO渠道留空）',
  callback_enabled TINYINT(1)  NOT NULL DEFAULT 1,
  status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  config_json     JSON         NULL COMMENT 'SSO校验接口base_url/app_key/加密app_secret/票据TTL（密钥加密存储、接口脱敏）',
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_channel_code (channel_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='提报渠道注册表';

CREATE TABLE IF NOT EXISTS demand_user (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'DemandHub OneID',
  name                VARCHAR(64)  NOT NULL,
  login_name          VARCHAR(64)  NULL COMMENT 'PC登录账号',
  password_hash       VARCHAR(100) NULL COMMENT 'BCrypt密码哈希（仅PC账号密码登录）',
  password_updated_at DATETIME(3)  NULL COMMENT 'NULL=需强制改密',
  phone               VARCHAR(32)  NULL,
  wecom_userid        VARCHAR(64)  NULL COMMENT '创金零售verify回传的企微userid',
  employee_no         VARCHAR(32)  NULL,
  email               VARCHAR(128) NULL,
  is_employee         TINYINT(1)   NOT NULL DEFAULT 0,
  primary_org_id      BIGINT UNSIGNED NULL,
  status              VARCHAR(16)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/ACTIVE/DISABLED/MERGED',
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

CREATE TABLE IF NOT EXISTS demand_org (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name            VARCHAR(128) NOT NULL,
  level           VARCHAR(16)  NOT NULL COMMENT 'LINE/DEPT/GROUP',
  parent_id       BIGINT UNSIGNED NOT NULL DEFAULT 0,
  path            VARCHAR(512) NOT NULL COMMENT '物化路径，如 /100/110/（尾斜杠，子树startsWith匹配）',
  org_kind        VARCHAR(16)  NULL COMMENT 'REPORTER/ASSIGNER/BOTH',
  external_flag   TINYINT(1)   NOT NULL DEFAULT 0,
  external_dept_id VARCHAR(32) NULL COMMENT '渠道侧部门ID（创金零售/企微部门ID），票据登录部门映射用',
  status          VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_parent (parent_id),
  KEY idx_path (path),
  KEY idx_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='组织树（管理员可CRUD）';

CREATE TABLE IF NOT EXISTS channel_user_mapping (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  channel_code    VARCHAR(32)  NOT NULL,
  channel_user_id VARCHAR(128) NOT NULL COMMENT '渠道侧用户唯一ID（CHUANGJIN_LS存企微userid）',
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

CREATE TABLE IF NOT EXISTS demand_role_grant (
  id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_user_id      BIGINT UNSIGNED NOT NULL COMMENT '引用 demand_user.id',
  role_code           VARCHAR(32)  NOT NULL COMMENT '角色族: ADMIN/EXECUTIVE/MANAGER/HANDLER；管哪类由demand_type_scope表达，管哪片由org_id子树表达',
  org_id              BIGINT UNSIGNED NULL,
  demand_type_scope   VARCHAR(256) NULL COMMENT '需求类型集合（逗号多选），NULL=跟随角色默认',
  effective_from      DATETIME(3) NULL,
  effective_to        DATETIME(3) NULL,
  granted_by          BIGINT UNSIGNED NULL COMMENT '授予人 demand_user.id',
  is_deleted          INT           NOT NULL DEFAULT 0 COMMENT '0=生效；回收时置为行id（uk_grant 含本列，避免已删行互撞）',
  created_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at          DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_grant (demand_user_id, role_code, org_id, demand_type_scope, is_deleted),
  KEY idx_org (org_id),
  KEY idx_role (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='业务角色本地授权';

-- ---------- 3) 种子：组织树（id 保留 100~141，path 尾斜杠格式） ----------
INSERT IGNORE INTO demand_org(id, name, level, parent_id, path, org_kind, external_flag, status) VALUES
(100, '创金合信零售业务线', 'LINE',  0,   '/100/',       'BOTH',     0, 'ACTIVE'),
(110, '财管科技产品部',     'DEPT',  100, '/100/110/',   'BOTH',     0, 'ACTIVE'),
(111, '科技产品一组',       'GROUP', 110, '/100/110/111/','ASSIGNER', 0, 'ACTIVE'),
(112, '科技产品二组',       'GROUP', 110, '/100/110/112/','ASSIGNER', 0, 'ACTIVE'),
(120, '客户陪伴服务部',     'DEPT',  100, '/100/120/',   'BOTH',     0, 'ACTIVE'),
(121, '客户陪伴一组',       'GROUP', 120, '/100/120/121/','ASSIGNER', 0, 'ACTIVE'),
(130, '培训开发部',         'DEPT',  100, '/100/130/',   'BOTH',     0, 'ACTIVE'),
(131, '培训开发一组',       'GROUP', 130, '/100/130/131/','ASSIGNER', 0, 'ACTIVE'),
(140, '零售一线营业部',     'DEPT',  100, '/100/140/',   'REPORTER', 0, 'ACTIVE'),
(141, '营业部一组',         'GROUP', 140, '/100/140/141/','REPORTER', 0, 'ACTIVE'),
-- 外部虚拟组织：创金零售票据部门未映射时的兜底挂载点（开发计划 3.5，不阻塞登录提报）
(900, '外部/待确认',        'DEPT',  0,   '/900/',       NULL,       1, 'ACTIVE');

-- ---------- 4) 种子：用户（id 保留 1001~1007；wecom_userid 为 dev Mock 值，test/prod 由 verify 回传真实企微userid） ----------
-- 首个 ADMIN（1001 张管理）：login_name=admin，初始密码 Admin@123456（BCrypt），password_updated_at=NULL 表示首次登录强制改密
INSERT IGNORE INTO demand_user(id, name, login_name, password_hash, password_updated_at, phone, wecom_userid, employee_no, email, is_employee, primary_org_id, status) VALUES
(1001, '张管理', 'admin', '$2b$10$l8x3YuZxjnhAEHHQSnL5oeHe7fmlC8AlyvYdYrWi0qSPYViSVaa0y', NULL, '13800001001', 'wq_u_admin_001',   'E1001', 'u_admin_001@demandhub.local',   1, 110, 'ACTIVE'),
(1002, '李总',   NULL, NULL, NULL, '13800001002', 'wq_u_exec_001',    'E1002', 'u_exec_001@demandhub.local',    1, 100, 'ACTIVE'),
(1003, '王经理', NULL, NULL, NULL, '13800001003', 'wq_u_mgr_tech',    'E1003', 'u_mgr_tech@demandhub.local',    1, 110, 'ACTIVE'),
(1004, '陈陪伴', NULL, NULL, NULL, '13800001004', 'wq_u_handler_a1',  'E1004', 'u_handler_a1@demandhub.local',  1, 121, 'ACTIVE'),
(1005, '刘培训', NULL, NULL, NULL, '13800001005', 'wq_u_handler_b1',  'E1005', 'u_handler_b1@demandhub.local',  1, 131, 'ACTIVE'),
(1006, '赵一线', NULL, NULL, NULL, '13800001006', 'wq_u_reporter_1',  'E1006', 'u_reporter_1@demandhub.local',  1, 141, 'ACTIVE'),
(1007, '钱一线', NULL, NULL, NULL, '13800001007', 'wq_u_reporter_2',  'E1007', 'u_reporter_2@demandhub.local',  1, 141, 'ACTIVE');

-- ---------- 5) 种子：渠道注册（一期启用 WEB + CHUANGJIN_LS，其余预留 DISABLED） ----------
-- CHUANGJIN_LS 的 config_json 为开发占位：dev 走内置 Mock SSO（channel-sso.mock=true），
-- test/prod 的 base_url/app_key/app_secret 经环境变量 CHANNEL_LS_* 注入，密钥不入库明文回显。
INSERT IGNORE INTO demand_channel(id, channel_code, channel_name, app_id, callback_enabled, status, config_json) VALUES
(1, 'WEB',          'PC管理端',     NULL, 0, 'ACTIVE',   NULL),
(2, 'CHUANGJIN_LS', '创金零售',     NULL, 0, 'ACTIVE',
 JSON_OBJECT('sso_verify_base_url', '', 'app_key', '', 'app_secret', '', 'ticket_ttl_seconds', 60)),
(3, 'WECOM_APP',    '企微应用(预留)', NULL, 0, 'DISABLED', NULL),
(4, 'WECOM_BOT',    '企微机器人(预留)', NULL, 1, 'DISABLED', NULL),
(5, 'FEISHU_BOT',   '飞书机器人(预留)', NULL, 1, 'DISABLED', NULL),
(6, 'DOUBAO_WORK',  '豆包工作(预留)',  NULL, 1, 'DISABLED', NULL),
(7, 'WORKBUDDY',    'WorkBuddy(预留)', NULL, 1, 'DISABLED', NULL),
(8, 'VOICE',        '语音渠道(预留)',  NULL, 1, 'DISABLED', NULL);

-- ---------- 6) 种子：渠道用户映射（dev：channel_user_id = 原 Mock wecomId） ----------
INSERT IGNORE INTO channel_user_mapping(channel_code, channel_user_id, demand_user_id, channel_name, channel_phone, channel_dept, match_type, bound_at) VALUES
('CHUANGJIN_LS', 'wq_u_admin_001',  1001, '张管理', '13800001001', '财管科技产品部', 'WECOMID', NOW(3)),
('CHUANGJIN_LS', 'wq_u_exec_001',   1002, '李总',   '13800001002', '创金合信零售业务线', 'WECOMID', NOW(3)),
('CHUANGJIN_LS', 'wq_u_mgr_tech',   1003, '王经理', '13800001003', '财管科技产品部', 'WECOMID', NOW(3)),
('CHUANGJIN_LS', 'wq_u_handler_a1', 1004, '陈陪伴', '13800001004', '客户陪伴一组', 'WECOMID', NOW(3)),
('CHUANGJIN_LS', 'wq_u_handler_b1', 1005, '刘培训', '13800001005', '培训开发一组', 'WECOMID', NOW(3)),
('CHUANGJIN_LS', 'wq_u_reporter_1', 1006, '赵一线', '13800001006', '营业部一组',   'WECOMID', NOW(3)),
('CHUANGJIN_LS', 'wq_u_reporter_2', 1007, '钱一线', '13800001007', '营业部一组',   'WECOMID', NOW(3));

-- ---------- 7) 种子：角色族授权（旧角色按开发计划 4.2 口径转换：DEMAND_MANAGER→MANAGER+type_scope，HANDLER→HANDLER+scope，REPORTER 丢弃） ----------
-- 组织映射推断：财管科技产品部(110)/科技产品一组(111)→TECH，客户陪伴一组(121)→MATL，培训开发一组(131)→TRAIN
INSERT IGNORE INTO demand_role_grant(demand_user_id, role_code, org_id, demand_type_scope, granted_by) VALUES
(1001, 'ADMIN',     NULL, NULL,   1001),
(1002, 'EXECUTIVE', NULL, NULL,   1001),
(1003, 'MANAGER',   110,  'TECH', 1001),
(1004, 'HANDLER',   121,  'MATL', 1001),
(1005, 'HANDLER',   131,  'TRAIN',1001),
-- 钱一线兼任科技产品一组处理人（科技池无独立 mock 处理人）
(1007, 'HANDLER',   111,  'TECH', 1001);

SET FOREIGN_KEY_CHECKS = 1;
