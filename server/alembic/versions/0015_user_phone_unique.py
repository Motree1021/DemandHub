"""0015 dh_user.phone 全表唯一（手机号可作登录账号）

背景（2026-10-18 需求）：新建 PC 用户时手机号必填，且手机号可作为登录账号。
作登录凭证必须全表唯一，否则登录时无法区分命中哪个人。

数据前置：渠道临时人的 phone 是早期种子带入的渠道快照脏数据（应用代码无任何
写入/消费方，用户管理也不再展示渠道用户），迁移前统一置 NULL；
MySQL 唯一索引允许多个 NULL，存量 PC 用户未填手机号不受影响。
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 渠道临时人的手机号是渠道快照脏数据（无消费方），置 NULL 腾出唯一空间
    op.execute("UPDATE dh_user SET phone = NULL WHERE channel <> 'ACCOUNT'")
    op.create_index("uk_user_phone", "dh_user", ["phone"], unique=True)


def downgrade() -> None:
    op.drop_index("uk_user_phone", table_name="dh_user")
