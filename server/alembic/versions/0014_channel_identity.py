"""OneID 一期：dh_channel_identity（渠道身份表）+ dh_identity_link_log（挂接审计表）+ 存量回填。

口径（2026-10-17 方案定稿，用户确认后开工）：
- 渠道身份独立成表：UNIQUE(channel, channel_user_id) = 一把渠道钥匙只属于一个人
- 渠道用户首次进门照旧自动建档（临时人，dh_user.channel != 'ACCOUNT'），可正常使用；
  管理员事后在「编辑 PC 用户」中把未归属渠道身份挂接到 PC 用户名下，历史数据自动归一
- PC 端用户（channel='ACCOUNT'）即 OneID 用户：挂接后渠道免登进入的即该 PC 用户
- 不做手机号自动撮合、不做用户自助绑定，唯一归并手段 = 管理员挂接
- 存量回填：非 ACCOUNT 用户每人生成一条渠道身份（指向自己，幂等）
- dh_user.wecom_userid 一期保留只读作对照，登录链路不再读取
- 排序规则跟随 dh_user 的 utf8mb4_unicode_ci（按 channel_user_id 与 dh_user.wecom_userid 关联，
  混用 0900_ai_ci 会报 Illegal mix of collations）
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    # ---- 渠道身份表（一行=一把渠道钥匙，只属于一个人） ----
    op.execute(sa.text("""
        CREATE TABLE dh_channel_identity (
          id                BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
          user_id           BIGINT      NOT NULL COMMENT '归属的人（dh_user.id；未归并=渠道临时人，挂接后=PC用户）',
          channel           VARCHAR(32) NOT NULL COMMENT '渠道码',
          channel_user_id   VARCHAR(64) NOT NULL COMMENT '渠道侧用户编号（企微 userid）',
          channel_user_name VARCHAR(64)          COMMENT '渠道侧姓名快照（每次进门更新，供管理员识别）',
          created_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '首次进门时间',
          updated_at        DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '最近进门时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_channel_identity (channel, channel_user_id),
          KEY ix_channel_identity_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='渠道身份（OneID：一把渠道钥匙只属于一个人）'
    """))

    # ---- 挂接/改挂审计表（行只增不改） ----
    op.execute(sa.text("""
        CREATE TABLE dh_identity_link_log (
          id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          action          VARCHAR(16)  NOT NULL COMMENT 'LINK（挂接）/REBIND（改挂）',
          identity_id     BIGINT       NOT NULL COMMENT '渠道身份（dh_channel_identity.id）',
          channel         VARCHAR(32)  NOT NULL COMMENT '渠道码快照',
          channel_user_id VARCHAR(64)  NOT NULL COMMENT '渠道侧用户编号快照',
          from_user_id    BIGINT       NOT NULL COMMENT '原归属人（dh_user.id）',
          from_user_name  VARCHAR(64)  NOT NULL COMMENT '原归属人姓名快照',
          to_user_id      BIGINT       NOT NULL COMMENT '新归属人（dh_user.id）',
          to_user_name    VARCHAR(64)  NOT NULL COMMENT '新归属人姓名快照',
          moved_counts    VARCHAR(512)          COMMENT '过户数据量明细 JSON（仅 LINK；REBIND 不搬数据为 NULL）',
          operator_id     BIGINT       NOT NULL COMMENT '操作人（dh_user.id）',
          operator_name   VARCHAR(64)  NOT NULL COMMENT '操作人姓名快照',
          created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '操作时间',
          PRIMARY KEY (id),
          KEY ix_link_log_identity (identity_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='OneID 挂接/改挂审计'
    """))

    # ---- 存量回填：非账密用户每人生成一条渠道身份（指向自己；按唯一键幂等） ----
    op.execute(sa.text("""
        INSERT IGNORE INTO dh_channel_identity (user_id, channel, channel_user_id, channel_user_name)
        SELECT id, channel, wecom_userid, name FROM dh_user
        WHERE channel <> 'ACCOUNT' AND wecom_userid IS NOT NULL AND wecom_userid <> ''
    """))


def downgrade():
    op.execute(sa.text("DROP TABLE IF EXISTS dh_identity_link_log"))
    op.execute(sa.text("DROP TABLE IF EXISTS dh_channel_identity"))
