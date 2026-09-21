-- =========================================================
-- DemandHub 阶段 7（M6 看板报表 + M9 AI Agent）增量建表与种子数据
-- 适用：已有 01~04 脚本的库直接执行（幂等，可重复执行）
-- 执行：docker exec -i demandhub-mysql mysql -uroot -pdemandhub123 demandhub < deploy/mysql/init/05-schema-m6m9.sql
-- =========================================================

SET NAMES utf8mb4;

USE demandhub;

-- ---------- M6：报表导出异步任务 ----------
CREATE TABLE IF NOT EXISTS report_export_task (
  id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  task_no      VARCHAR(64)  NOT NULL COMMENT '任务编号 RPT-YYYYMMDD-NNN',
  report_type  VARCHAR(32)  NOT NULL COMMENT 'DEMAND_LIST 需求清单 / MONTHLY_REVIEW 月度复盘',
  params_json  TEXT         NULL COMMENT '导出筛选参数 JSON',
  requester_id BIGINT UNSIGNED NOT NULL COMMENT '发起人用户数值ID',
  status       VARCHAR(16)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/FAILED',
  file_path    VARCHAR(512) NULL COMMENT 'MinIO 对象路径',
  file_name    VARCHAR(256) NULL,
  error_msg    VARCHAR(512) NULL,
  created_at   DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  finished_at  DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_task_no (task_no),
  KEY idx_requester (requester_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报表导出异步任务（M6）';

-- ---------- M9：Agent 会话 ----------
CREATE TABLE IF NOT EXISTS agent_session (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_no  VARCHAR(64)  NOT NULL COMMENT '会话编号（UUID）',
  user_id     BIGINT UNSIGNED NOT NULL COMMENT '会话归属用户',
  scene       VARCHAR(32)  NOT NULL COMMENT 'SUBMIT_GUIDE 提报启发 / HANDLE_ASSIST 处理辅助',
  demand_id   BIGINT UNSIGNED NULL COMMENT '处理辅助场景关联需求',
  title       VARCHAR(256) NULL COMMENT '会话标题（首条用户消息截断）',
  status      VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/CLOSED',
  created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_session_no (session_no),
  KEY idx_user_scene (user_id, scene, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 会话（M9）';

-- ---------- M9：Agent 会话消息 ----------
CREATE TABLE IF NOT EXISTS agent_message (
  id                 BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  session_id         BIGINT UNSIGNED NOT NULL,
  role               VARCHAR(16)  NOT NULL COMMENT 'USER/ASSISTANT/SYSTEM',
  content            TEXT         NOT NULL,
  structured_payload TEXT         NULL COMMENT '结构化产出 JSON（如表单字段回填）',
  created_at         DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_session (session_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 会话消息（M9）';

-- ---------- M9：Agent 产出草稿区（AI 生成需人工确认） ----------
CREATE TABLE IF NOT EXISTS agent_draft (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id        BIGINT UNSIGNED NOT NULL,
  session_id       BIGINT UNSIGNED NULL,
  draft_type       VARCHAR(32)  NOT NULL COMMENT 'QUESTIONS 调研问题清单 / SOLUTION 方案初稿',
  content          TEXT         NOT NULL,
  status           VARCHAR(16)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING 待确认 / CONFIRMED 已入库 / DISCARDED 已废弃',
  confirmed_by     BIGINT UNSIGNED NULL,
  confirmed_at     DATETIME(3) NULL,
  target_solution_id BIGINT UNSIGNED NULL COMMENT '确认后写入的 solution.id',
  created_by       BIGINT UNSIGNED NOT NULL,
  created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_demand_type (demand_id, draft_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 产出草稿区（确认后才入正式表）';

-- ---------- M9：Prompt 模板（可配置） ----------
CREATE TABLE IF NOT EXISTS agent_prompt_template (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  template_code VARCHAR(64)  NOT NULL COMMENT 'SUBMIT_GUIDE/HANDLE_ASSIST_QUESTIONS/HANDLE_ASSIST_SOLUTION',
  template_name VARCHAR(128) NOT NULL,
  content       TEXT         NOT NULL COMMENT 'Prompt 模板，支持 ${var} 占位',
  status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  remark        VARCHAR(512) NULL,
  created_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at    DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_template_code (template_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent Prompt 模板（一期存库，二期可迁 Nacos）';

-- ---------- M9：RAG 知识库（向量 JSON 列存储，可替换 pgvector） ----------
CREATE TABLE IF NOT EXISTS knowledge_doc (
  id               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  demand_id        BIGINT UNSIGNED NOT NULL COMMENT '来源需求（DONE）',
  demand_no        VARCHAR(64)  NOT NULL,
  title            VARCHAR(256) NOT NULL,
  demand_type_code VARCHAR(32)  NOT NULL,
  content          TEXT         NOT NULL COMMENT '向量化文本（方案+评审意见+SOP 摘要）',
  embedding        JSON         NOT NULL COMMENT '向量（一期 Mock embedding，JSON 数组；二期可换 pgvector VECTOR 列）',
  status           VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
  created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_demand (demand_id),
  KEY idx_type (demand_type_code, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG 知识库（验收通过后异步入库）';

-- ---------- M6：报表就绪通知模板 ----------
INSERT IGNORE INTO notification_template(template_code, template_name, title_template, content_template, remark) VALUES
('REPORT_READY', '报表导出就绪', '报表已就绪：${report_name}', '您导出的报表「${report_name}」已生成，点击本通知下载（链接 7 天内有效）。', '报表导出异步任务完成后站内通知');

-- ---------- M9：Prompt 模板种子 ----------
INSERT IGNORE INTO agent_prompt_template(template_code, template_name, content, remark) VALUES
('SUBMIT_GUIDE', '提报启发对话', '你是 DemandHub 的提报助手。用户描述：${user_message}。当前表单已填：${form_context}。请追问缺失字段（标题/类型/描述/紧急程度/期望交付），并在信息充分时输出结构化字段。', '提报启发 Agent 系统提示词'),
('HANDLE_ASSIST_QUESTIONS', '调研问题清单生成', '基于需求「${title}」（${demand_type}）描述：${content}，以及相似历史需求：${similar_docs}，生成处理前的调研问题清单。', '处理辅助 Agent - 调研问题'),
('HANDLE_ASSIST_SOLUTION', '方案初稿生成', '基于需求「${title}」（${demand_type}）描述：${content}，参考相似历史方案：${similar_docs}，生成方案初稿（需求理解 + 方案内容）。输出仅作草稿，需人工确认。', '处理辅助 Agent - 方案初稿');
