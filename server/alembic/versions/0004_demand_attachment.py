"""新建需求附件表 demand_attachment（微需求快速通道·阶段一：图片/文档附件随需求流转）。

- 仅存元数据与存储键，文件本体在服务端本地目录（attachment_dir 配置），storage_key 不外泄
- 软删（status=DELETED）：DRAFT 态可传可删，提交后不可删，保证受理方看到的附件可追溯
"""
import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        CREATE TABLE demand_attachment (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          demand_id   BIGINT       NOT NULL COMMENT '需求/草稿 id（demand.id）',
          file_name   VARCHAR(256) NOT NULL COMMENT '原始文件名（展示与下载名）',
          kind        VARCHAR(16)  NOT NULL COMMENT '附件类别：IMAGE/DOC',
          file_ext    VARCHAR(16)  NOT NULL COMMENT '扩展名（小写，白名单校验后的安全值）',
          size        INT          NOT NULL COMMENT '文件大小（字节）',
          storage_key VARCHAR(128) NOT NULL COMMENT '存储键（uuid，服务端目录内相对定位，不外泄）',
          uploaded_by BIGINT       NOT NULL COMMENT '上传人 dh_user.id',
          status      VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE' COMMENT 'ACTIVE/DELETED（软删）',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '上传时间',
          updated_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uq_attachment_storage_key (storage_key),
          KEY ix_attachment_demand_id (demand_id, id),
          CONSTRAINT fk_attachment_demand FOREIGN KEY (demand_id) REFERENCES demand(id),
          CONSTRAINT fk_attachment_user   FOREIGN KEY (uploaded_by) REFERENCES dh_user(id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='需求附件（图片/文档，随需求一并流转）'
    """))


def downgrade():
    op.drop_table("demand_attachment")
