"""角色默认值 HANDLER → REPORTER：渠道新用户建档默认「提报人」（最小权限）。

- 只改 dh_user.role 的列默认值，存量数据一律不动（2026-10-16 拍板：老用户角色由管理员按需手工调整）
- REPORTER 不参与任何角色守卫/状态机规则，提报/补充/验收等提报人动作本就只校验登录态与归属
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("dh_user", "role", server_default="REPORTER",
                    existing_type=sa.String(16), existing_nullable=False)


def downgrade():
    op.alter_column("dh_user", "role", server_default="HANDLER",
                    existing_type=sa.String(16), existing_nullable=False)
