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
