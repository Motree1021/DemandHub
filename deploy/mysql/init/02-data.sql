-- =========================================================
-- DemandHub 初始化数据 v1.1
-- 来源：DemandHub_系统数据库设计_v1.1 第 5 节
-- =========================================================

USE demandhub;

-- ---------- 需求类型初始化 ----------
INSERT INTO demand_type(type_code, type_name, default_org_id, state_machine_key, sort) VALUES
('TECH',  '科技需求', /* 财管科技产品部 org_id */ NULL, 'DEFAULT', 1),
('MATL',  '物料需求', /* 客户陪伴服务部 org_id */ NULL, 'DEFAULT', 2),
('TRAIN', '培训需求', /* 培训开发部 org_id */     NULL, 'DEFAULT', 3);

-- ---------- 通用字典初始化 ----------
INSERT INTO sys_dict(dict_type, item_code, item_name, sort) VALUES
('URGENCY','NORMAL',  '普通', 1),
('URGENCY','URGENT',  '紧急', 2),
('URGENCY','CRITICAL','特急', 3),
('CLOSE_REASON','NOT_ACCEPTED','不受理',1),
('CLOSE_REASON','DUPLICATE',   '重复需求',2),
('CLOSE_REASON','REVOKED',     '提报人撤销',3),
('HOLD_REASON','WAIT_EXTERNAL','等待外部依赖',1),
('HOLD_REASON','WAIT_RESOURCE','等待资源',2),
('HOLD_REASON','OTHER',        '其他',9);

-- ---------- 通知模板初始化（阶段 4，template_code = 状态机事件名 / SLA_ALERT） ----------
INSERT INTO notification_template(template_code, template_name, title_template, content_template, remark) VALUES
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

-- ---------- SLA 默认配置 ----------
INSERT INTO sla_config(demand_type_code, status, warn_minutes, max_minutes, remark) VALUES
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
