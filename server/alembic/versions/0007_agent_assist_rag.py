"""P3 AI 处理辅助 + RAG：agent_draft 草稿表、rag_vector 向量表、agent_session 唯一约束改 (demand_id, scene)。

- agent_draft：处理辅助产出草稿区（PENDING → CONFIRMED/DISCARDED）；确认方案初稿才写 solution 表
- rag_vector：DONE 需求向量化知识库（对应蓝本 knowledge_doc；demand_id 唯一幂等）
- agent_session：唯一约束从 demand_id 单列改为 (demand_id, scene)，一个需求可并存
  SUBMIT_GUIDE（提报启发）与 HANDLE_ASSIST（处理辅助）两类会话
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    # ---- 处理辅助草稿区 ----
    op.execute(sa.text("""
        CREATE TABLE agent_draft (
          id                 BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id          BIGINT       NOT NULL COMMENT 'FK demand.id',
          session_id         BIGINT       NOT NULL COMMENT 'FK agent_session.id',
          draft_type         VARCHAR(16)  NOT NULL COMMENT 'QUESTIONS 调研问题 / SOLUTION 方案初稿',
          content            MEDIUMTEXT   NOT NULL COMMENT '草稿内容 JSON（questions[] 或 {specContent,solutionContent}）',
          status             VARCHAR(16)  NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING/CONFIRMED/DISCARDED',
          created_by         BIGINT       NOT NULL COMMENT '生成操作人 FK dh_user.id',
          confirmed_by       BIGINT                COMMENT '确认/废弃操作人',
          confirmed_at       DATETIME(3)           COMMENT '确认/废弃时间',
          target_solution_id BIGINT                COMMENT '确认入库的 solution.id',
          created_at         DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at         DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          KEY idx_agent_draft_demand (demand_id),
          CONSTRAINT fk_agent_draft_demand FOREIGN KEY (demand_id) REFERENCES demand (id),
          CONSTRAINT fk_agent_draft_session FOREIGN KEY (session_id) REFERENCES agent_session (id),
          CONSTRAINT fk_agent_draft_creator FOREIGN KEY (created_by) REFERENCES dh_user (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='处理辅助 Agent 草稿区'
    """))

    # ---- RAG 向量知识库（对应蓝本 knowledge_doc） ----
    op.execute(sa.text("""
        CREATE TABLE rag_vector (
          id               BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id        BIGINT       NOT NULL COMMENT 'FK demand.id（唯一：重复向量化幂等跳过）',
          demand_no        VARCHAR(40)  NOT NULL COMMENT '需求编号（冗余，相似卡片直出）',
          title            VARCHAR(256) NOT NULL COMMENT '需求标题（冗余）',
          demand_type_code VARCHAR(16)           COMMENT '需求类型码（冗余）',
          content          MEDIUMTEXT   NOT NULL COMMENT '向量化原文（标题+描述+最新方案+评审意见）',
          embedding        MEDIUMTEXT   NOT NULL COMMENT '向量 JSON 数组（L2 归一化）',
          status           VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/INACTIVE',
          vectorized_at    DATETIME(3)  NOT NULL COMMENT '向量化时间',
          created_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at       DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_rag_vector_demand (demand_id),
          KEY idx_rag_vector_status (status),
          CONSTRAINT fk_rag_vector_demand FOREIGN KEY (demand_id) REFERENCES demand (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='RAG 需求向量知识库'
    """))

    # ---- agent_session 唯一约束：demand_id 单列 → (demand_id, scene) ----
    # 先建复合唯一索引再删旧单列索引：外键要求 demand_id 作最左列的索引始终存在（MySQL 1553）
    op.create_unique_constraint("uk_agent_session_demand_scene", "agent_session", ["demand_id", "scene"])
    op.drop_index("demand_id", table_name="agent_session")


def downgrade():
    op.drop_constraint("uk_agent_session_demand_scene", "agent_session", type_="unique")
    op.create_index("demand_id", "agent_session", ["demand_id"], unique=True)
    op.drop_table("rag_vector")
    op.drop_table("agent_draft")
