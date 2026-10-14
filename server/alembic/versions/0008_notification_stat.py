"""P4 通知与统计：通知/模板/偏好/去重/SLA 配置/日统计/导出任务/角色授权八表 + demand 组织两列（只建不用）。

- notification：站内信信箱（一期只写 IN_APP 行，写入即送达；WECOM 渠道列保留二期用）
- notification_template：按事件编码的模板（${var} 占位，缺失变量渲染为空串），含 19 条种子
- notification_preference：用户按类型关闭非关键通知；TODO 待办提醒不可关闭不落库
- notify_dedupe：通知去重表（替 Redis setIfAbsent+TTL；冲突且未过期=跳过，事务回滚=下轮重试）
- sla_config：类型 × 状态停留阈值（黄/红两档），含 11 条种子
- demand_stat_daily：日统计预聚合（组织维度一期写 0，待组织域启用）
- report_export_task：报表导出异步任务（file_path 落本地目录，替代 MinIO）
- demand_role_grant：业务角色本地授权（EXECUTIVE/MANAGER；type_scope 逗号多选，NULL=全类型）
- demand.assignee_org_id / submitter_org_id：组织维度留口（一期只建不用，org 过滤待 P5）
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    # ---- 通知消息（信箱） ----
    op.execute(sa.text("""
        CREATE TABLE notification (
          id            BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id     BIGINT                COMMENT '关联需求（报表就绪等系统通知可空）',
          receiver_id   BIGINT       NOT NULL COMMENT '接收人 FK dh_user.id',
          channel       VARCHAR(16)  NOT NULL DEFAULT 'IN_APP' COMMENT 'IN_APP 站内 / WECOM 企微（二期）',
          template_code VARCHAR(64)           COMMENT '模板编码（事件名/SLA_ALERT/REPORT_READY）',
          title         VARCHAR(256) NOT NULL,
          content       TEXT                  COMMENT '正文',
          link          VARCHAR(512)          COMMENT '跳转链接（需求详情/报表任务页）',
          is_read       TINYINT(1)   NOT NULL DEFAULT 0,
          read_at       DATETIME(3)           COMMENT '阅读时间',
          send_status   VARCHAR(16)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/SENT/FAILED（IN_APP 写入即 SENT）',
          retry_count   INT          NOT NULL DEFAULT 0 COMMENT '企微推送重试计数（二期）',
          created_at    DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          sent_at       DATETIME(3)           COMMENT '送达时间',
          PRIMARY KEY (id),
          KEY idx_receiver_unread (receiver_id, is_read),
          KEY idx_demand (demand_id),
          CONSTRAINT fk_notification_receiver FOREIGN KEY (receiver_id) REFERENCES dh_user (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='通知消息（信箱表，替代 MQ）'
    """))

    # ---- 通知模板 ----
    op.execute(sa.text("""
        CREATE TABLE notification_template (
          id               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          template_code    VARCHAR(64)  NOT NULL COMMENT '模板编码（状态机事件名/SLA_ALERT/REPORT_READY）',
          template_name    VARCHAR(128) NOT NULL,
          title_template   VARCHAR(256) NOT NULL COMMENT '标题模板，${var} 占位',
          content_template TEXT         NOT NULL COMMENT '正文模板，${var} 占位',
          status           VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
          remark           VARCHAR(512),
          created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_template_code (template_code)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='通知模板'
    """))

    # ---- 用户通知偏好 ----
    op.execute(sa.text("""
        CREATE TABLE notification_preference (
          id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
          user_id     BIGINT      NOT NULL COMMENT 'FK dh_user.id',
          notify_type VARCHAR(32) NOT NULL COMMENT 'STATUS_CHANGE/MENTION/ASSIGN/REVIEW_REQUEST/ACCEPTANCE_REQUEST/SLA_ALERT',
          enabled     TINYINT(1)  NOT NULL DEFAULT 1,
          created_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at  DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_user_type (user_id, notify_type),
          CONSTRAINT fk_preference_user FOREIGN KEY (user_id) REFERENCES dh_user (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户通知偏好（TODO 待办提醒不可关闭，不落库）'
    """))

    # ---- 通知去重（替 Redis setIfAbsent + 7 天 TTL） ----
    op.execute(sa.text("""
        CREATE TABLE notify_dedupe (
          id         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          dedupe_key VARCHAR(128) NOT NULL COMMENT '去重键，如 sla:alert:RED:{demandId}:{status}',
          created_at DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '标记时间（7 天过期由扫描侧判断）',
          PRIMARY KEY (id),
          UNIQUE KEY uk_dedupe_key (dedupe_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='通知去重（替 Redis）'
    """))

    # ---- SLA 停留时长配置 ----
    op.execute(sa.text("""
        CREATE TABLE sla_config (
          id               BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_type_code VARCHAR(32) NOT NULL,
          status           VARCHAR(32) NOT NULL COMMENT '停留状态，如 SUBMITTED/TRIAGE/IN_PROGRESS',
          warn_minutes     INT         NOT NULL COMMENT '黄色预警阈值（分钟）',
          max_minutes      INT         NOT NULL COMMENT '红色告警阈值（分钟）',
          enabled          TINYINT(1)  NOT NULL DEFAULT 1,
          remark           VARCHAR(512),
          created_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at       DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_type_status (demand_type_code, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='SLA 停留时长配置（类型 × 状态）'
    """))

    # ---- 需求日统计预聚合 ----
    op.execute(sa.text("""
        CREATE TABLE demand_stat_daily (
          id               BIGINT         NOT NULL AUTO_INCREMENT COMMENT '主键',
          stat_date        DATE           NOT NULL,
          demand_type_code VARCHAR(32)    NOT NULL,
          assignee_org_id  BIGINT         NOT NULL DEFAULT 0 COMMENT '承接组织（一期写 0，待组织域）',
          reporter_org_id  BIGINT         NOT NULL DEFAULT 0 COMMENT '提报组织（一期写 0，待组织域）',
          status           VARCHAR(32)    NOT NULL,
          cnt              INT            NOT NULL DEFAULT 0,
          avg_cycle_hours  DECIMAL(10,2)           COMMENT '已关闭需求平均交付周期（小时）',
          updated_at       DATETIME(3)    NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_dim (stat_date, demand_type_code, assignee_org_id, reporter_org_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求日统计预聚合'
    """))

    # ---- 报表导出异步任务 ----
    op.execute(sa.text("""
        CREATE TABLE report_export_task (
          id           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          task_no      VARCHAR(64)  NOT NULL COMMENT '任务编号 RPT-YYYYMMDD-NNN',
          report_type  VARCHAR(32)  NOT NULL COMMENT 'DEMAND_LIST 需求清单 / MONTHLY_REVIEW 月度复盘（二期）',
          params_json  TEXT                  COMMENT '导出筛选参数 JSON',
          requester_id BIGINT       NOT NULL COMMENT '发起人 FK dh_user.id',
          status       VARCHAR(16)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/RUNNING/SUCCESS/FAILED',
          file_path    VARCHAR(512)          COMMENT '本地文件路径（替代 MinIO 对象路径）',
          file_name    VARCHAR(256),
          error_msg    VARCHAR(512),
          created_at   DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          finished_at  DATETIME(3)           COMMENT '完成时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_task_no (task_no),
          KEY idx_requester (requester_id, status),
          CONSTRAINT fk_report_requester FOREIGN KEY (requester_id) REFERENCES dh_user (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='报表导出异步任务'
    """))

    # ---- 业务角色本地授权 ----
    op.execute(sa.text("""
        CREATE TABLE demand_role_grant (
          id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          user_id           BIGINT       NOT NULL COMMENT '被授权人 FK dh_user.id',
          role_code         VARCHAR(32)  NOT NULL COMMENT 'ADMIN/EXECUTIVE/MANAGER/HANDLER',
          org_id            BIGINT                COMMENT '授权组织（一期留口，待组织域）',
          demand_type_scope VARCHAR(256)          COMMENT '需求类型集合（逗号多选），NULL=全部类型',
          effective_from    DATETIME(3)          COMMENT '生效起（NULL=立即）',
          effective_to      DATETIME(3)          COMMENT '生效止（NULL=长期）',
          granted_by        BIGINT                COMMENT '授予人 FK dh_user.id',
          is_deleted        INT          NOT NULL DEFAULT 0 COMMENT '0=生效；回收时置为行 id',
          created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_grant (user_id, role_code, org_id, demand_type_scope, is_deleted),
          KEY idx_role (role_code),
          CONSTRAINT fk_grant_user FOREIGN KEY (user_id) REFERENCES dh_user (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='业务角色本地授权'
    """))

    # ---- demand 组织维度留口（一期只建不用：看板 Top10 走 submitter_dept 快照） ----
    op.execute(sa.text("""
        ALTER TABLE demand
          ADD COLUMN assignee_org_id  BIGINT NULL COMMENT '承接组织（一期只建不用，待组织域）' AFTER assignee_id,
          ADD COLUMN submitter_org_id BIGINT NULL COMMENT '提报组织（一期只建不用，待组织域）' AFTER assignee_org_id
    """))

    # ---- 种子：通知模板（18 事件 + REPORT_READY；变量 ${var} 缺失渲染为空串） ----
    op.execute(sa.text("""
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
        ('SLA_ALERT',         'SLA 告警',      'SLA ${level_text}：${demand_no}',    '需求 ${demand_no}「${title}」在状态「${to_status}」已停留 ${elapsed_minutes} 分钟，超过${level_text}阈值，请及时跟进。', '即将超时黄色预警 / 已超时红色告警'),
        ('REPORT_READY',      '报表导出就绪',   '报表已就绪：${report_name}',        '您导出的报表「${report_name}」已生成，点击本通知下载（链接 7 天内有效）。', '报表导出异步任务完成后站内通知')
    """))

    # ---- 种子：SLA 默认配置 ----
    op.execute(sa.text("""
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
        ('TRAIN','IN_PROGRESS',  7200, 14400,NULL)
    """))


def downgrade():
    op.execute(sa.text("ALTER TABLE demand DROP COLUMN assignee_org_id, DROP COLUMN submitter_org_id"))
    for table in ("demand_role_grant", "report_export_task", "demand_stat_daily", "sla_config",
                  "notify_dedupe", "notification_preference", "notification_template", "notification"):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
