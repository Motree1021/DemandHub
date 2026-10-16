"""dh_user 加 type_scope：按人统一的需求类型权限（2026-10-16 拍板）。

- 存逗号分隔类型码（如 "TECH,MATL"）；NULL/空 = 无权限（严格口径，管理员/提报人除外）
- 仅对业务角色（EXECUTIVE/MANAGER/HANDLER）生效；ADMIN 全类型直通，REPORTER 不受限
- 存量用户一律为 NULL = 无权限，由管理员在用户管理手工补配（拍板：不做补救脚本）
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dh_user", sa.Column("type_scope", sa.String(64), nullable=True,
                                       comment="需求类型权限（逗号分隔类型码，空=无权限）"))


def downgrade():
    op.drop_column("dh_user", "type_scope")
