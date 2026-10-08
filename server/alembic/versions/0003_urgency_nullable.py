"""demand.urgency 取消默认值并允许为空：紧急程度不再默认"普通"，提交前必须经追问与用户确认。"""
import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("demand", "urgency", existing_type=sa.String(16), nullable=True, server_default=None)


def downgrade():
    op.execute("UPDATE demand SET urgency = 'NORMAL' WHERE urgency IS NULL")
    op.alter_column("demand", "urgency", existing_type=sa.String(16), nullable=False, server_default="NORMAL")
