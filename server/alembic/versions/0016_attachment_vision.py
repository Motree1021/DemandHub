"""0016 demand_attachment AI 图片识别（2026-10-22 拍板）

背景：H5 提报页新增「让 AI 读懂图片」入口——用户上传微信/企微聊天截图，
视觉模型把图转写为文本后走既有对话链路整理需求；与默认「AI 不看附件内容」
的 archive 口径并存（用户显式选择才触发识别）。

新增四列：
- purpose：用途（archive 存档 / parse AI 图片识别），存量数据默认 archive；
- parse_status：解析状态（PARSED/NO_TEXT/FAILED），仅 purpose=parse 时有值；
- parsed_text：视觉模型转写文本，供受理方追溯（会话里同内容另有一条用户消息）；
- parsed_at：解析完成时间。
"""

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "demand_attachment",
        sa.Column("purpose", sa.String(20), nullable=False, server_default="archive",
                  comment="用途：archive 存档 / parse AI 图片识别"),
    )
    op.add_column(
        "demand_attachment",
        sa.Column("parse_status", sa.String(20), nullable=True,
                  comment="解析状态：PARSED/NO_TEXT/FAILED（purpose=parse 时才有值）"),
    )
    op.add_column(
        "demand_attachment",
        sa.Column("parsed_text", sa.Text, nullable=True,
                  comment="视觉模型转写文本（供受理方追溯）"),
    )
    op.add_column(
        "demand_attachment",
        sa.Column("parsed_at", DATETIME(fsp=3), nullable=True, comment="解析完成时间"),
    )
    op.create_index("ix_attachment_purpose", "demand_attachment", ["purpose"])


def downgrade() -> None:
    op.drop_index("ix_attachment_purpose", table_name="demand_attachment")
    op.drop_column("demand_attachment", "parsed_at")
    op.drop_column("demand_attachment", "parsed_text")
    op.drop_column("demand_attachment", "parse_status")
    op.drop_column("demand_attachment", "purpose")
