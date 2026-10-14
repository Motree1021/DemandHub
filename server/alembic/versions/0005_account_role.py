"""P1 账号与权限：dh_user 增账密/角色列，新建 refresh_token 表，种子初始 ADMIN。

- 账密用户无企微身份，wecom_userid 落占位值 acct:<login_account>（方案A，不改既有非空唯一约束）
- 初始 ADMIN 密码从环境变量 ADMIN_INITIAL_PASSWORD 读取（绝不硬编码）；未配置时跳过种子并告警
- must_change_pwd=True 强制首登改密
"""
import os

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("dh_user", sa.Column("login_account", sa.String(64), nullable=True, comment="账密登录账号，SSO 用户为空"))
    op.add_column("dh_user", sa.Column("password_hash", sa.String(128), nullable=True, comment="BCrypt 密码哈希，绝不明文"))
    op.add_column("dh_user", sa.Column("must_change_pwd", sa.Boolean(), nullable=False, server_default="0", comment="首登强制改密标记"))
    op.add_column("dh_user", sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0", comment="连续登录失败次数"))
    op.add_column("dh_user", sa.Column("locked_until", mysql.DATETIME(fsp=3), nullable=True, comment="锁定截止时间，过期自动解锁"))
    op.add_column("dh_user", sa.Column("role", sa.String(16), nullable=False, server_default="HANDLER", comment="角色：ADMIN/HANDLER"))
    op.create_index("uk_dh_user_login_account", "dh_user", ["login_account"], unique=True)

    op.execute(sa.text("""
        CREATE TABLE refresh_token (
          id          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          user_id     BIGINT       NOT NULL COMMENT 'FK dh_user.id',
          token_hash  VARCHAR(128) NOT NULL COMMENT 'refresh token 哈希，不落原文',
          expires_at  DATETIME(3)  NOT NULL COMMENT '过期时间',
          revoked     TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '是否已吊销（旋转/登出/改密时置1）',
          created_at  DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '签发时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_refresh_token_hash (token_hash),
          KEY idx_refresh_token_user (user_id),
          CONSTRAINT fk_refresh_token_user FOREIGN KEY (user_id) REFERENCES dh_user (id)
        ) COMMENT='续期凭证：access token 过期后换新票用，每用一次旋转吊销旧票'
    """))

    _seed_initial_admin()


def _seed_initial_admin():
    password = os.environ.get("ADMIN_INITIAL_PASSWORD", "").strip()
    if not password:
        print("[0005] 警告：未配置 ADMIN_INITIAL_PASSWORD，跳过初始 ADMIN 种子；"
              "配置后重新执行迁移或手工建号")
        return
    from passlib.context import CryptContext
    password_hash = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO dh_user (name, wecom_userid, channel, status, role,
                             login_account, password_hash, must_change_pwd, fail_count)
        SELECT '系统管理员', 'acct:admin', 'ACCOUNT', 'ACTIVE', 'ADMIN',
               'admin', :password_hash, 1, 0
        FROM DUAL
        WHERE NOT EXISTS (SELECT 1 FROM dh_user WHERE login_account = 'admin')
    """), {"password_hash": password_hash})


def downgrade():
    op.drop_table("refresh_token")
    op.drop_index("uk_dh_user_login_account", table_name="dh_user")
    for column in ("role", "locked_until", "fail_count", "must_change_pwd", "password_hash", "login_account"):
        op.drop_column("dh_user", column)
