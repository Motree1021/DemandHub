-- =========================================================
-- DemandHub 阶段 4（M7 通知中心 + M8 系统管理）增量建表与种子数据
-- 适用：已有 01-schema.sql + 02-data.sql 的库直接执行（幂等，可重复执行）
-- 执行：docker exec -i demandhub-mysql mysql -uroot -pdemandhub123 demandhub < deploy/mysql/init/04-schema-m7m8.sql
-- =========================================================

USE demandhub;

-- ---------- 通知模板 ----------
CREATE TABLE IF NOT EXISTS notification_template (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  template_code    VARCHAR(64)  NOT NULL COMMENT '模板编码（按事件），如 SUBMIT/ASSIGN/SLA_ALERT',
  template_name    VARCHAR(128) NOT NULL,
  title_template   VARCHAR(256) NOT NULL COMMENT '标题模板，支持 ${var} 占位',
  content_template TEXT         NOT NULL COMMENT '正文模板，支持 ${var} 占位',
  status           VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  remark           VARCHAR(512) NULL,
  created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_template_code (template_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通知模板';

-- ---------- 用户通知偏好 ----------
CREATE TABLE IF NOT EXISTS notification_preference (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL COMMENT '用户数值ID（demand_user_snapshot.id）',
  notify_type VARCHAR(32) NOT NULL COMMENT 'STATUS_CHANGE/MENTION/ASSIGN/REVIEW_REQUEST/ACCEPTANCE_REQUEST/SLA_ALERT',
  enabled     TINYINT(1) NOT NULL DEFAULT 1,
  created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_type (user_id, notify_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户通知偏好（待办提醒 TODO 不可关闭，不落库）';

-- ---------- SLA 停留时长配置 ----------
CREATE TABLE IF NOT EXISTS sla_config (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_type_code VARCHAR(32) NOT NULL,
  status           VARCHAR(32) NOT NULL COMMENT '停留状态，如 SUBMITTED/TRIAGE/IN_PROGRESS',
  warn_minutes     INT NOT NULL COMMENT '黄色预警阈值（分钟）',
  max_minutes      INT NOT NULL COMMENT '红色告警阈值（分钟）',
  enabled          TINYINT(1) NOT NULL DEFAULT 1,
  remark           VARCHAR(512) NULL,
  created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_type_status (demand_type_code, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='SLA 停留时长配置（类型 × 状态）';

-- ---------- 状态机配置（热加载） ----------
CREATE TABLE IF NOT EXISTS state_machine_config (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  config_key  VARCHAR(64)  NOT NULL COMMENT '配置标识，demand_type.state_machine_key 引用',
  config_name VARCHAR(128) NOT NULL,
  config_json MEDIUMTEXT   NOT NULL COMMENT '流转规则 JSON：{"rules":[{"from","event","to","roles","remark"}]}',
  status      VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  remark      VARCHAR(512) NULL,
  created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_config_key (config_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='状态机配置（热加载，无需重启）';

-- ---------- 通知模板种子（template_code = 状态机事件名 / SLA_ALERT） ----------
-- 可用变量：${demand_no} ${title} ${operator_name} ${from_status} ${to_status} ${comment} ${link} ${level_text} ${elapsed_minutes}
INSERT IGNORE INTO notification_template(template_code, template_name, title_template, content_template, remark) VALUES
('SUBMIT',            '需求提交提醒',   '新需求待受理：${demand_no}',        '需求 ${demand_no}「${title}」已由 ${operator_name} 提交，请及时受理。', '通知承接组织经理'),
('WITHDRAW',          '需求撤销提醒',   '需求已撤销：${demand_no}',          '需求 ${demand_no}「${title}」已被提报人撤销。', NULL),
('ACCEPT',            '受理通过提醒',   '需求已受理：${demand_no}',          '您提报的需求 ${demand_no}「${title}」已受理，进入需求池。', NULL),
('RETURN',            '退回补充提醒',   '需求退回补充：${demand_no}',        '您提报的需求 ${demand_no}「${title}」被退回补充，原因：${comment}。请补充后重新提交。', NULL),
('CLOSE',             '需求关闭提醒',   '需求已关闭：${demand_no}',          '需求 ${demand_no}「${title}」已关闭，原因：${comment}。', NULL),
('ASSIGN',            '任务分派提醒',   '新任务分派：${demand_no}',          '需求 ${demand_no}「${title}」已由 ${operator_name} 分派给你，请及时处理。', NULL),
('CLAIM',             '需求领取提醒',   '需求已被领取：${demand_no}',        '您提报的需求 ${demand_no}「${title}」已被处理人领取，进入分析阶段。', NULL),
('SUBMIT_REVIEW',     '方案评审请求',   '方案待评审：${demand_no}',          '需求 ${demand_no}「${title}」已提交方案评审，请及时评审。', NULL),
('REVIEW_PASS',       '评审通过提醒',   '方案评审通过：${demand_no}',        '需求 ${demand_no}「${title}」的方案评审已通过。', NULL),
('REVIEW_REJECT',     '评审打回提醒',   '方案评审打回：${demand_no}',        '需求 ${demand_no}「${title}」的方案评审被打回，意见：${comment}。', NULL),
('START',             '开始处理提醒',   '需求开始处理：${demand_no}',        '您提报的需求 ${demand_no}「${title}」已开始处理。', NULL),
('SUBMIT_ACCEPTANCE', '验收请求提醒',   '需求待验收：${demand_no}',          '您提报的需求 ${demand_no}「${title}」已提交验收，请及时验收。', NULL),
('ACCEPT_PASS',       '验收通过提醒',   '验收通过：${demand_no}',            '需求 ${demand_no}「${title}」验收通过，已归档。', NULL),
('ACCEPT_REJECT',     '验收打回提醒',   '验收打回：${demand_no}',            '需求 ${demand_no}「${title}」验收未通过，意见：${comment}。请继续处理。', NULL),
('CHANGE_TYPE',       '类型修正提醒',   '需求类型已修正：${demand_no}',      '需求 ${demand_no}「${title}」类型已由 ${from_type} 修正为 ${to_type}，重新路由。', NULL),
('HOLD',              '需求挂起提醒',   '需求已挂起：${demand_no}',          '需求 ${demand_no}「${title}」已挂起，原因：${comment}。', NULL),
('RESUME',            '需求恢复提醒',   '需求已恢复：${demand_no}',          '需求 ${demand_no}「${title}」已恢复处理。', NULL),
('SLA_ALERT',         'SLA 告警',      'SLA ${level_text}：${demand_no}',    '需求 ${demand_no}「${title}」在状态「${to_status}」已停留 ${elapsed_minutes} 分钟，超过${level_text}阈值，请及时跟进。', '即将超时黄色预警 / 已超时红色告警');

-- ---------- SLA 默认配置（可按需调整，自测时可改为 1 分钟） ----------
INSERT IGNORE INTO sla_config(demand_type_code, status, warn_minutes, max_minutes, remark) VALUES
('TECH', 'SUBMITTED',    1440, 2880, '受理时限：1天预警 / 2天告警'),
('TECH', 'TRIAGE',       1440, 2880, '分派时限'),
('TECH', 'ANALYZING',    4320, 7200, '分析时限：3天 / 5天'),
('TECH', 'IN_PROGRESS',  7200, 14400,'处理时限：5天 / 10天'),
('TECH', 'ACCEPTANCE',   1440, 2880, '验收时限'),
('MATL', 'SUBMITTED',    1440, 2880, NULL),
('MATL', 'TRIAGE',       1440, 2880, NULL),
('MATL', 'IN_PROGRESS',  7200, 14400,NULL),
('TRAIN','SUBMITTED',    1440, 2880, NULL),
('TRAIN','TRIAGE',       1440, 2880, NULL),
('TRAIN','IN_PROGRESS',  7200, 14400,NULL);
