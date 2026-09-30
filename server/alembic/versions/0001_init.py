"""创建六张 MVP 业务表，无旧版数据迁移。"""
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def pk():
    return sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True)


def timestamps():
    return [sa.Column(name, DATETIME(fsp=3), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP(3)"))
            for name in ("created_at", "updated_at")]


def upgrade():
    op.create_table("dh_user", pk(), sa.Column("name", sa.String(64), nullable=False),
        sa.Column("wecom_userid", sa.String(64), nullable=False, unique=True),
        sa.Column("phone", sa.String(32)), sa.Column("employee_no", sa.String(32)),
        sa.Column("email", sa.String(128)), sa.Column("dept_id", sa.String(32)),
        sa.Column("dept_name", sa.String(128)), sa.Column("dept_path", sa.String(512)),
        sa.Column("channel", sa.String(32), nullable=False, server_default="CHUANGJIN_LS"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("last_login_at", DATETIME(fsp=3)), *timestamps(), comment="渠道回源用户")
    op.create_table("prompt_version", pk(), sa.Column("code", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("snapshot", sa.JSON(), nullable=False), timestamps()[0], comment="不可变标准与提示词快照")
    op.create_table("demand", pk(), sa.Column("demand_no", sa.String(40), unique=True),
        sa.Column("title", sa.String(256)), sa.Column("demand_type_code", sa.String(32)),
        sa.Column("subtype_code", sa.String(32)), sa.Column("content", sa.Text()),
        sa.Column("urgency", sa.String(16), nullable=False, server_default="NORMAL"),
        sa.Column("expect_delivery_at", sa.Date()), sa.Column("ext", sa.JSON(), nullable=False),
        sa.Column("quality", sa.JSON()), sa.Column("field_sources", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("client_request_id", sa.String(64), nullable=False),
        sa.Column("create_request_hash", sa.String(64), nullable=False),
        sa.Column("standard_version_id", sa.BigInteger(), sa.ForeignKey("prompt_version.id")),
        sa.Column("quality_content_hash", sa.String(64)),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("submitter_id", sa.BigInteger(), sa.ForeignKey("dh_user.id"), nullable=False),
        sa.Column("submitter_name", sa.String(64)), sa.Column("submitter_dept", sa.String(128)),
        sa.Column("channel", sa.String(32)), sa.Column("session_id", sa.BigInteger(), unique=True),
        sa.Column("submitted_at", DATETIME(fsp=3)), sa.Column("closed_at", DATETIME(fsp=3)),
        sa.Column("close_reason", sa.String(256)), *timestamps(),
        sa.UniqueConstraint("submitter_id", "client_request_id", name="uq_demand_create"), comment="草稿与正式需求")
    op.create_index("ix_demand_owner_status", "demand", ["submitter_id", "status"])
    op.create_index("ix_demand_type_status", "demand", ["demand_type_code", "status"])
    op.create_index("ix_demand_submitted", "demand", ["submitted_at"])
    op.create_table("demand_no_seq", sa.Column("biz_date", sa.Date(), primary_key=True),
        sa.Column("type_code", sa.String(32), primary_key=True),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"), comment="按类型按日编号流水")
    op.create_table("agent_session", pk(), sa.Column("session_no", sa.String(64), nullable=False, unique=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("dh_user.id"), nullable=False),
        sa.Column("scene", sa.String(32), nullable=False),
        sa.Column("demand_id", sa.BigInteger(), sa.ForeignKey("demand.id"), nullable=False, unique=True),
        sa.Column("title", sa.String(256)), sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("asked_target", sa.String(64)), *timestamps(), comment="每份草稿唯一启发会话")
    op.create_table("agent_message", pk(),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("agent_session.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_payload", sa.JSON()), sa.Column("request_id", sa.String(64)),
        sa.Column("request_hash", sa.String(64)),
        sa.Column("prompt_version_id", sa.BigInteger(), sa.ForeignKey("prompt_version.id")),
        sa.Column("model", sa.String(64)), sa.Column("prompt_tokens", sa.Integer()),
        sa.Column("completion_tokens", sa.Integer()), sa.Column("latency_ms", sa.Integer()), timestamps()[0],
        sa.UniqueConstraint("session_id", "request_id", "role", name="uq_message_request_role"), comment="Agent 消息与幂等响应")


def downgrade():
    for table in ("agent_message", "agent_session", "demand_no_seq", "demand", "prompt_version", "dh_user"):
        op.drop_table(table)
