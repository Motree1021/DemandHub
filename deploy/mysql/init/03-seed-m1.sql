-- =========================================================
-- DemandHub 阶段 2（M1）开发自测种子数据
-- 前提：06-rebuild-user-domain.sql 已完成用户域重建与种子（组织/用户/渠道映射/角色授权）
-- 执行：docker exec -i demandhub-mysql mysql -uroot -pdemandhub123 demandhub < deploy/mysql/init/03-seed-m1.sql
-- 说明：用户/组织/授权种子由 06 脚本维护，本文件只维护需求类型路由与示例需求
-- =========================================================

SET NAMES utf8mb4;

USE demandhub;

-- ---------- 需求类型默认承接组织（路由到叶子承接组，与处理人授权层级一致） ----------
UPDATE demand_type SET default_org_id = 111 WHERE type_code = 'TECH';
UPDATE demand_type SET default_org_id = 121 WHERE type_code = 'MATL';
UPDATE demand_type SET default_org_id = 131 WHERE type_code = 'TRAIN';

-- ---------- 示例需求（越权用例自测；角色授权见 06-rebuild-user-domain.sql） ----------
-- D1: 赵一线提报 → 科技一组(111)   | 期望可见：reporter_1 / mgr_tech / exec
-- D2: 赵一线提报 → 客户陪伴一组(121)| 期望可见：reporter_1 / handler_a1 / exec
-- D3: 钱一线提报 → 培训开发一组(131)| 期望可见：reporter_2 / handler_b1 / exec
-- D4: 钱一线提报 → 客户陪伴一组(121)| 期望可见：reporter_2 / handler_a1 / exec
INSERT IGNORE INTO demand(demand_no, title, demand_type_code, content, urgency, status, submitter_id, submitter_org_id, assignee_org_id, submitted_at) VALUES
('TECH-20260920-001', '手机银行首页加载优化', 'TECH', '首页首屏加载超过 4 秒，影响一线展业演示。', 'URGENT', 'SUBMITTED', 1006, 141, 111, '2026-09-20 09:00:00'),
('MATL-20260920-002', '四季度客户活动物料印制', 'MATL', '四季度路演需要折页 5000 份、易拉宝 20 个。', 'NORMAL', 'SUBMITTED', 1006, 141, 121, '2026-09-20 09:10:00'),
('TRAIN-20260920-003', '新员工基金从业培训', 'TRAIN', '11 月新入职 12 人需要从业资格考前培训。', 'NORMAL', 'SUBMITTED', 1007, 141, 131, '2026-09-20 09:20:00'),
('MATL-20260920-004', '营业部展业手册更新', 'MATL', '展业手册需更新三季度产品数据。', 'NORMAL', 'SUBMITTED', 1007, 141, 121, '2026-09-20 09:30:00');
