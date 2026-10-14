"""P2 状态机与全流程流转：demand 增流转列、8 张流转协作表、附件扩展 bizType/bizId、种子状态机配置。

- 角色仍只有 ADMIN/HANDLER；蓝本中 MANAGER/EXECUTIVE 动作由 ADMIN 承担（状态机规则 ADMIN 直通）
- ON_HOLD 为叠加态：主状态列不变，靠 hold_snapshot_status/hold_reason 非空表达挂起
- 状态机配置热重载：state_machine_config 表 + DEFAULT 种子规则
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    # ---- demand 增列 ----
    op.add_column("demand", sa.Column("assignee_id", sa.BigInteger(), nullable=True, comment="当前处理人 FK dh_user.id"))
    op.add_column("demand", sa.Column("hold_snapshot_status", sa.String(32), nullable=True, comment="挂起前主状态；非空即挂起中（叠加态）"))
    op.add_column("demand", sa.Column("hold_reason", sa.String(256), nullable=True, comment="挂起原因"))
    op.add_column("demand", sa.Column("confirmed_at", mysql.DATETIME(fsp=3), nullable=True, comment="方案评审通过时间"))
    op.add_column("demand", sa.Column("done_at", mysql.DATETIME(fsp=3), nullable=True, comment="验收通过时间"))
    op.add_column("demand", sa.Column("quality_score", sa.SmallInteger(), nullable=True, comment="验收质量评分 1-5"))
    op.add_column("demand", sa.Column("satisfaction_score", sa.SmallInteger(), nullable=True, comment="验收满意度评分 1-5"))

    op.create_index("ix_demand_assignee_status", "demand", ["assignee_id", "status"], unique=False)
    op.create_index("ix_demand_hold_snapshot", "demand", ["hold_snapshot_status"], unique=False)
    op.create_foreign_key("fk_demand_assignee", "demand", "dh_user", ["assignee_id"], ["id"])

    # ---- 附件表扩展 bizType/bizId（兼容存量） ----
    op.add_column("demand_attachment", sa.Column("biz_type", sa.String(16), nullable=False, server_default="DEMAND", comment="附件归属类型：DRAFT/DEMAND/SOLUTION/COMMENT"))
    op.add_column("demand_attachment", sa.Column("biz_id", sa.BigInteger(), nullable=True, comment="业务对象 id（SOLUTION/COMMENT 用），DEMAND 时同 demand_id"))
    op.alter_column("demand_attachment", "biz_type", server_default=None)

    # ---- 状态机配置表 ----
    op.execute(sa.text("""
        CREATE TABLE state_machine_config (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          config_key  VARCHAR(64)  NOT NULL COMMENT '配置标识（如 DEFAULT）',
          config_name VARCHAR(128) NOT NULL COMMENT '配置名称',
          config_json MEDIUMTEXT   NOT NULL COMMENT '规则 JSON',
          version     INT          NOT NULL DEFAULT 1 COMMENT '版本号，每次更新+1，热重载判断依据',
          status      VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/INACTIVE',
          remark      VARCHAR(512)          COMMENT '备注',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_sm_config_key (config_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='状态机规则配置（热重载）'
    """))

    # ---- 流转日志 ----
    op.execute(sa.text("""
        CREATE TABLE demand_transition_log (
          id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id         BIGINT       NOT NULL COMMENT 'FK demand.id',
          from_status       VARCHAR(32)           COMMENT '源状态（拆分建单类事件可为空）',
          to_status         VARCHAR(32)  NOT NULL COMMENT '目标状态',
          event             VARCHAR(64)  NOT NULL COMMENT '事件名',
          operator_id       BIGINT       NOT NULL COMMENT '操作人 FK dh_user.id',
          operator_snapshot VARCHAR(128)          COMMENT '操作人姓名快照',
          hold_flag         TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否挂起/恢复类事件',
          comment           TEXT                  COMMENT '备注',
          extra             JSON                  COMMENT '扩展信息（JSON）',
          created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '发生时间',
          PRIMARY KEY (id),
          KEY idx_transition_demand_time (demand_id, created_at),
          CONSTRAINT fk_transition_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_transition_operator FOREIGN KEY (operator_id) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求状态流转日志（每次流转必写）'
    """))

    # ---- 分派/领取/退单记录 ----
    op.execute(sa.text("""
        CREATE TABLE assignment (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id   BIGINT       NOT NULL COMMENT 'FK demand.id',
          from_user_id BIGINT             COMMENT '原处理人（退回池时用）',
          to_user_id   BIGINT             COMMENT '新处理人',
          action      VARCHAR(16)  NOT NULL COMMENT 'ASSIGN/CLAIM/RETURN',
          operator_id BIGINT       NOT NULL COMMENT '操作人 FK dh_user.id',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '发生时间',
          PRIMARY KEY (id),
          KEY idx_assignment_demand (demand_id),
          KEY idx_assignment_to (to_user_id, action),
          CONSTRAINT fk_assignment_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_assignment_operator FOREIGN KEY (operator_id) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求分派领取记录'
    """))

    # ---- 方案 ----
    op.execute(sa.text("""
        CREATE TABLE solution (
          id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id         BIGINT       NOT NULL COMMENT 'FK demand.id',
          version           INT          NOT NULL COMMENT '版本号，每份方案递增',
          author_id         BIGINT       NOT NULL COMMENT '作者 FK dh_user.id',
          spec_content      TEXT                  COMMENT '需求规约',
          solution_content  TEXT                  COMMENT '方案内容',
          plan_delivery_at  DATE                  COMMENT '计划交付时间（评审联动字段）',
          status            VARCHAR(16)  NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT/SUBMITTED/APPROVED/REJECTED',
          remark            VARCHAR(512)          COMMENT '备注',
          created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_solution_demand_version (demand_id, version),
          KEY idx_solution_demand (demand_id),
          CONSTRAINT fk_solution_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_solution_author FOREIGN KEY (author_id) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求方案'
    """))

    # ---- 评审 ----
    op.execute(sa.text("""
        CREATE TABLE review (
          id                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id          BIGINT       NOT NULL COMMENT 'FK demand.id',
          review_type        VARCHAR(16)  NOT NULL COMMENT 'SOLUTION/ACCEPTANCE',
          target_id          BIGINT                COMMENT 'SOLUTION 评审时 FK solution.id',
          result             VARCHAR(16)  NOT NULL COMMENT 'PASS/REJECT',
          opinion            TEXT                  COMMENT '评审意见（REJECT 必填）',
          quality_score      TINYINT UNSIGNED      COMMENT '质量评分 1-5（验收 PASS 必填）',
          satisfaction_score TINYINT UNSIGNED      COMMENT '满意度评分 1-5（验收 PASS 必填）',
          reviewer_id        BIGINT       NOT NULL COMMENT '评审人 FK dh_user.id',
          created_at         DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '评审时间',
          PRIMARY KEY (id),
          KEY idx_review_demand_type (demand_id, review_type),
          CONSTRAINT fk_review_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_review_solution FOREIGN KEY (target_id) REFERENCES solution(id),
          CONSTRAINT fk_review_reviewer FOREIGN KEY (reviewer_id) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='方案与验收评审记录（留痕不可改）'
    """))

    # ---- 评论 ----
    op.execute(sa.text("""
        CREATE TABLE comment (
          id                BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id         BIGINT       NOT NULL COMMENT 'FK demand.id',
          author_id         BIGINT       NOT NULL COMMENT '作者 FK dh_user.id',
          content           TEXT         NOT NULL COMMENT '评论内容',
          mentioned_user_ids VARCHAR(512)         COMMENT '@用户 id 列表，逗号分隔',
          created_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at        DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          KEY idx_comment_demand_time (demand_id, created_at),
          CONSTRAINT fk_comment_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_comment_author FOREIGN KEY (author_id) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求评论（仅作者可改，不可删）'
    """))

    # ---- 工时 ----
    op.execute(sa.text("""
        CREATE TABLE effort_log (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id   BIGINT       NOT NULL COMMENT 'FK demand.id',
          user_id     BIGINT       NOT NULL COMMENT '登记人 FK dh_user.id',
          hours       DECIMAL(5,1) NOT NULL DEFAULT 0 COMMENT '工时（0<h≤24）',
          work_date   DATE         NOT NULL COMMENT '工作日期',
          remark      VARCHAR(512)         COMMENT '备注',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          KEY idx_effort_demand (demand_id),
          KEY idx_effort_user_date (user_id, work_date),
          CONSTRAINT fk_effort_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_effort_user FOREIGN KEY (user_id) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求工时记录'
    """))

    # ---- 需求关系 ----
    op.execute(sa.text("""
        CREATE TABLE demand_relation (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          from_id     BIGINT       NOT NULL COMMENT '源需求 id',
          to_id       BIGINT       NOT NULL COMMENT '目标需求 id',
          type        VARCHAR(16)  NOT NULL COMMENT 'PARENT/DEPENDS/DUPLICATE/SPLIT',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_relation_pair (from_id, to_id, type),
          KEY idx_relation_to (to_id),
          CONSTRAINT fk_relation_from FOREIGN KEY (from_id) REFERENCES demand(id),
          CONSTRAINT fk_relation_to FOREIGN KEY (to_id) REFERENCES demand(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求关系（父子/依赖/重复/拆分）'
    """))

    _seed_state_machine_config()


def _seed_state_machine_config():
    """种子默认规则：ADMIN 承担蓝本中 MANAGER/EXECUTIVE 全部动作。"""
    import json
    rules = [
        # 提报侧
        {"from": "DRAFT", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "提交需求"},
        {"from": "NEED_INFO", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "补充后重新提交"},
        {"from": "DRAFT", "event": "WITHDRAW", "to": "CLOSED", "roles": [], "remark": "撤销草稿"},
        {"from": "SUBMITTED", "event": "WITHDRAW", "to": "CLOSED", "roles": [], "remark": "提报人撤销"},
        {"from": "NEED_INFO", "event": "WITHDRAW", "to": "CLOSED", "roles": [], "remark": "待补充撤销"},
        # 受理
        {"from": "SUBMITTED", "event": "ACCEPT", "to": "TRIAGE", "roles": ["ADMIN"], "remark": "受理通过"},
        {"from": "SUBMITTED", "event": "RETURN", "to": "NEED_INFO", "roles": ["ADMIN"], "remark": "退回补充"},
        {"from": "SUBMITTED", "event": "CLOSE", "to": "CLOSED", "roles": ["ADMIN"], "remark": "不受理/重复关闭"},
        {"from": "TRIAGE", "event": "CLOSE", "to": "CLOSED", "roles": ["ADMIN"], "remark": "待分派关闭"},
        # 分派/领取/退单
        {"from": "TRIAGE", "event": "ASSIGN", "to": "ANALYZING", "roles": ["ADMIN"], "remark": "经理分派"},
        {"from": "TRIAGE", "event": "CLAIM", "to": "ANALYZING", "roles": ["HANDLER"], "remark": "处理人领取"},
        {"from": "ANALYZING", "event": "RETURN_POOL", "to": "TRIAGE", "roles": ["HANDLER", "ADMIN"], "remark": "退回处理池"},
        # 分析/方案评审
        {"from": "ANALYZING", "event": "SUBMIT_REVIEW", "to": "SOLUTION_REVIEW", "roles": ["HANDLER"], "remark": "提交方案评审"},
        {"from": "SOLUTION_REVIEW", "event": "REVIEW_PASS", "to": "CONFIRMED", "roles": ["ADMIN"], "remark": "评审通过"},
        {"from": "SOLUTION_REVIEW", "event": "REVIEW_REJECT", "to": "ANALYZING", "roles": ["ADMIN"], "remark": "评审打回"},
        # 处理/验收
        {"from": "CONFIRMED", "event": "START", "to": "IN_PROGRESS", "roles": ["HANDLER"], "remark": "开始处理"},
        {"from": "IN_PROGRESS", "event": "SUBMIT_ACCEPTANCE", "to": "ACCEPTANCE", "roles": ["HANDLER"], "remark": "提交验收"},
        {"from": "ACCEPTANCE", "event": "ACCEPT_PASS", "to": "DONE", "roles": [], "remark": "验收通过"},
        {"from": "ACCEPTANCE", "event": "ACCEPT_REJECT", "to": "IN_PROGRESS", "roles": [], "remark": "验收打回"},
        # 类型修正
        {"from": "SUBMITTED", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "NEED_INFO", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "TRIAGE", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "ANALYZING", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "SOLUTION_REVIEW", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "CONFIRMED", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "IN_PROGRESS", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        {"from": "ACCEPTANCE", "event": "CHANGE_TYPE", "to": None, "roles": ["ADMIN"], "remark": "类型修正"},
        # 挂起/恢复
        {"from": "ANALYZING", "event": "HOLD", "to": None, "roles": ["HANDLER", "ADMIN"], "remark": "挂起"},
        {"from": "SOLUTION_REVIEW", "event": "HOLD", "to": None, "roles": ["HANDLER", "ADMIN"], "remark": "挂起"},
        {"from": "CONFIRMED", "event": "HOLD", "to": None, "roles": ["HANDLER", "ADMIN"], "remark": "挂起"},
        {"from": "IN_PROGRESS", "event": "HOLD", "to": None, "roles": ["HANDLER", "ADMIN"], "remark": "挂起"},
        {"from": "ON_HOLD", "event": "RESUME", "to": None, "roles": ["HANDLER", "ADMIN"], "remark": "恢复"},
    ]
    config_json = json.dumps({"rules": rules}, ensure_ascii=False)
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO state_machine_config (config_key, config_name, config_json, version, status, remark)
        SELECT 'DEFAULT', '默认状态机', :config_json, 1, 'ACTIVE', '12态全流程'
        FROM DUAL
        WHERE NOT EXISTS (SELECT 1 FROM state_machine_config WHERE config_key = 'DEFAULT')
    """), {"config_json": config_json})


def downgrade():
    op.drop_table("demand_relation")
    op.drop_table("effort_log")
    op.drop_table("comment")
    op.drop_table("review")
    op.drop_table("solution")
    op.drop_table("assignment")
    op.drop_table("demand_transition_log")
    op.drop_table("state_machine_config")
    op.drop_column("demand_attachment", "biz_id")
    op.drop_column("demand_attachment", "biz_type")
    op.drop_constraint("fk_demand_assignee", "demand", type_="foreignkey")
    op.drop_index("ix_demand_hold_snapshot", table_name="demand")
    op.drop_index("ix_demand_assignee_status", table_name="demand")
    for column in ("satisfaction_score", "quality_score", "done_at", "confirmed_at", "hold_reason", "hold_snapshot_status", "assignee_id"):
        op.drop_column("demand", column)
