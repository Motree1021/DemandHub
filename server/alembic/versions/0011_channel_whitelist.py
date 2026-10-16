"""渠道白名单：demand_channel_whitelist + 操作留痕表 + demand_channel 白名单开关/联系引导两列。

口径（2026-10-16 方案定稿）：
- 独立白名单表管「允许谁进」，dh_user 仍只管「谁登录过」（登录时自动建档，不预建）
- 全局开关 whitelist_enabled 默认 0（关闭=全放行，登记完备后管理员手动开启，避免上线瞬间误伤存量）
- 拦截页联系引导 whitelist_contact 挂渠道行，公开接口读取（被拦用户无登录态也能展示）
- 移除白名单为硬删（留痕表保留完整历史），不删用户档案
- 排序规则必须跟随 dh_user 的 utf8mb4_unicode_ci（白名单表按 wecom_userid 与 dh_user 关联，
  混用 0900_ai_ci 会报 Illegal mix of collations）
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    # ---- 渠道行：白名单开关 + 拦截页联系引导 ----
    op.execute(sa.text("""
        ALTER TABLE demand_channel
          ADD COLUMN whitelist_enabled TINYINT(1)  NOT NULL DEFAULT 0 COMMENT '渠道白名单校验开关（0=全放行）' AFTER status,
          ADD COLUMN whitelist_contact VARCHAR(255) NULL COMMENT '拦截页联系引导文案' AFTER whitelist_enabled
    """))

    # ---- 渠道白名单（允许谁进；与 dh_user 用户档案相互独立） ----
    op.execute(sa.text("""
        CREATE TABLE demand_channel_whitelist (
          id              BIGINT      NOT NULL AUTO_INCREMENT COMMENT '主键',
          channel_code    VARCHAR(32) NOT NULL COMMENT '渠道码',
          channel_user_id VARCHAR(64) NOT NULL COMMENT '渠道侧用户ID（企微 userid）',
          display_name    VARCHAR(64)          COMMENT '登记姓名（选填，便于核对）',
          status          VARCHAR(16) NOT NULL DEFAULT 'ENABLED' COMMENT 'ENABLED/DISABLED',
          created_by      BIGINT               COMMENT '登记人（dh_user.id）',
          created_by_name VARCHAR(64)          COMMENT '登记人姓名快照',
          created_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '创建时间',
          updated_at      DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT '更新时间',
          PRIMARY KEY (id),
          UNIQUE KEY uk_whitelist_user (channel_code, channel_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='渠道白名单'
    """))

    # ---- 白名单操作留痕（增/删/启停/开关/文案全量落痕） ----
    op.execute(sa.text("""
        CREATE TABLE demand_channel_whitelist_log (
          id              BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
          action          VARCHAR(24)  NOT NULL COMMENT 'ADD/ENABLE/DISABLE/REMOVE/SWITCH_ON/SWITCH_OFF/UPDATE_CONTACT',
          channel_code    VARCHAR(32)  NOT NULL COMMENT '渠道码',
          channel_user_id VARCHAR(64)           COMMENT '操作对象企微ID（开关/文案类为 NULL）',
          operator_id     BIGINT       NOT NULL COMMENT '操作人（dh_user.id）',
          operator_name   VARCHAR(64)  NOT NULL COMMENT '操作人姓名快照',
          detail          VARCHAR(512)          COMMENT '补充信息（前后值/批量标注/移除对象快照）',
          created_at      DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT '操作时间',
          PRIMARY KEY (id),
          KEY ix_whitelist_log_channel (channel_code, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='渠道白名单操作留痕'
    """))


def downgrade():
    op.execute(sa.text("DROP TABLE IF EXISTS demand_channel_whitelist_log"))
    op.execute(sa.text("DROP TABLE IF EXISTS demand_channel_whitelist"))
    op.execute(sa.text("""
        ALTER TABLE demand_channel
          DROP COLUMN whitelist_enabled,
          DROP COLUMN whitelist_contact
    """))
