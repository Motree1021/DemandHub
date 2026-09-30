SET NAMES utf8mb4;
-- =====================================================================
-- P10：科技需求要素完善（基于 Wiegers《软件需求》与需求启发理论）
-- 1) demand_ext_tech 增加 tech_subtype（需求子类，驱动差异化表单）
-- 2) sys_dict 新增 TECH_SUBTYPE / RELATED_SYSTEM 字典
-- 3) agent_prompt_template.SUBMIT_GUIDE 升级为要素质量评估 rubric 提示词
--    （一期 Mock 的规则在 MockLlmClient，此模板供二期真实 LLM 使用）
-- 幂等：ALTER 前检查列是否存在；字典 INSERT IGNORE；模板 UPDATE 可重复执行
-- 注意：回滚脚本不入 init/（docker-entrypoint-initdb.d 会按字母序自动执行）
-- =====================================================================

USE demandhub;

-- ---------- 1) demand_ext_tech.tech_subtype ----------
SET @sql := IF((SELECT COUNT(*) FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA='demandhub' AND TABLE_NAME='demand_ext_tech' AND COLUMN_NAME='tech_subtype') = 0,
               'ALTER TABLE demand_ext_tech ADD COLUMN tech_subtype VARCHAR(32) NULL COMMENT ''需求子类（TECH_SUBTYPE 字典）'' AFTER demand_id',
               'SELECT 1');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ---------- 2) 字典：需求子类 / 关联系统 ----------
INSERT IGNORE INTO sys_dict(dict_type, item_code, item_name, sort) VALUES
('TECH_SUBTYPE','SYS_DEV', '系统开发', 1),
('TECH_SUBTYPE','DATA_RPT','数据报表', 2),
('TECH_SUBTYPE','SYS_INT', '系统集成', 3),
('TECH_SUBTYPE','OPS_OPT', '运维优化', 4),
('TECH_SUBTYPE','OTHER',  '其他',     5);

-- 存储值取 item_name（与历史自由文本兼容，详情页直接可读）；ADMIN 可在字典管理维护
INSERT IGNORE INTO sys_dict(dict_type, item_code, item_name, sort) VALUES
('RELATED_SYSTEM','DIRECT_SALES', '代销系统',     1),
('RELATED_SYSTEM','CRM',          'CRM',          2),
('RELATED_SYSTEM','DATA_CENTER',  '数据中心',     3),
('RELATED_SYSTEM','ORG_PLATFORM', '机构服务平台', 4),
('RELATED_SYSTEM','PORTAL',       '官网/APP',     5),
('RELATED_SYSTEM','OTHER',        '其他',         6);

-- ---------- 3) SUBMIT_GUIDE 提示词升级（要素 rubric + 追问阶梯，供二期真实 LLM） ----------
UPDATE agent_prompt_template SET
  content = '你是 DemandHub 的提报助手，用大白话帮助提报人把需求说清楚，禁止使用「业务需求/用户需求/功能需求」等分层术语。输入可能是：随口几句话、粘贴的一大段描述、或语音转文字（含口语词如"那个/嗯/就是"，需容错解析）。当前表单已填：${form_context}。任务：1) 从用户输入中抽取要素：标题/类型/紧急程度/期望交付/科技子类(系统开发/数据报表/系统集成/运维优化)/关联系统/业务场景/验收标准/价值与影响；2) 逐项评估质量：OK(具体可检验)/VAGUE(模糊)/MISSING(未填)/SKIP(用户说不知道或跳过)。VAGUE 判定：含歧义词（尽快/好用/方便/优化一下/越快越好/体验好）或缺少可检验事实（数字/时间/频率/误差）。3) 追问策略：同一要素最多追问2次——第1次复述并指出缺什么，第2次给句式模板和示例，仍不到位给选项或允许"后续补充"（标SKIP后不再问）；追问时先解释动机（"为了承接方准确评估"），不否定用户；信息齐备时列出已理解要素清单请用户确认。输出：结构化字段 + 各要素质量状态 + 下一轮追问（如有）。',
  remark = '提报启发 Agent 系统提示词（P10 升级：要素 rubric 四态 + 追问阶梯 + 口语容错）'
WHERE template_code = 'SUBMIT_GUIDE';
