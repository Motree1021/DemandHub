"""demand 表新增五区要素承载列与实例切分接缝列，新建要素变更留痕表 demand_change_log。

对齐《概念模型与数据库设计 v1.1》§5 定稿 DDL：
- demand.elements：A/B/C/D 区要素值（PRD 五区表单，标准配置驱动）
- demand.split_from_id / split_group_id：BR-T11 实例切分自引用接缝（一期仅预留）
- demand_change_log：要素级变更留痕（E7，FR-06 修改对话审计）
预算/IRB 字段不建（PRD §11 接缝，恢复时零 DDL）。
"""
import sqlalchemy as sa

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    # 概念模型 §5.1 定稿 DDL
    op.execute(sa.text("""
        ALTER TABLE demand
          ADD COLUMN elements JSON NULL COMMENT 'A/B/C/D 区要素值（PRD 五区表单，标准配置驱动）' AFTER ext,
          ADD COLUMN split_from_id BIGINT NULL COMMENT '实例切分来源需求 id（BR-T11，NULL=独立需求）' AFTER session_id,
          ADD COLUMN split_group_id CHAR(36) NULL COMMENT '同源拆分批次 UUID（B7 关联需求/追踪矩阵）' AFTER split_from_id,
          ADD INDEX ix_demand_split_group (split_group_id),
          ADD INDEX ix_demand_split_from (split_from_id),
          ADD CONSTRAINT fk_demand_split_from FOREIGN KEY (split_from_id) REFERENCES demand(id)
    """))
    # 概念模型 §5.2 定稿 DDL
    op.execute(sa.text("""
        CREATE TABLE demand_change_log (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id   BIGINT       NOT NULL COMMENT '需求/草稿 id（demand.id）',
          field_key   VARCHAR(64)  NOT NULL COMMENT '要素 key：B1/D8/ext.techSubtype/quality.* 等',
          old_value   JSON         NULL COMMENT '修改前值',
          new_value   JSON         NULL COMMENT '修改后值',
          source      VARCHAR(16)  NOT NULL DEFAULT 'user' COMMENT '来源：user/agent/default',
          changed_by  BIGINT       NULL COMMENT '操作人 dh_user.id；Agent 写入为 NULL',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '留痕时间',
          PRIMARY KEY (id),
          KEY ix_change_demand_time (demand_id, created_at),
          CONSTRAINT fk_change_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_change_user   FOREIGN KEY (changed_by) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求要素变更留痕（E7）'
    """))


def downgrade():
    op.drop_table("demand_change_log")
    op.drop_constraint("fk_demand_split_from", "demand", type_="foreignkey")
    op.drop_index("ix_demand_split_from", "demand")
    op.drop_index("ix_demand_split_group", "demand")
    op.drop_column("demand", "split_group_id")
    op.drop_column("demand", "split_from_id")
    op.drop_column("demand", "elements")
