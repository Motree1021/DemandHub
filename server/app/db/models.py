from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), default=now, onupdate=now, server_default=text("CURRENT_TIMESTAMP(3)"))


class User(Timestamps, Base):
    __tablename__ = "dh_user"
    __table_args__ = {"comment": "渠道回源用户"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    wecom_userid: Mapped[str] = mapped_column(String(64), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    employee_no: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    dept_id: Mapped[str | None] = mapped_column(String(32))
    dept_name: Mapped[str | None] = mapped_column(String(128))
    dept_path: Mapped[str | None] = mapped_column(String(512))
    channel: Mapped[str] = mapped_column(String(32), default="CHUANGJIN_LS", server_default="CHUANGJIN_LS")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))


class PromptVersion(Base):
    __tablename__ = "prompt_version"
    __table_args__ = {"comment": "不可变标准与提示词快照"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)"))


class Demand(Timestamps, Base):
    __tablename__ = "demand"
    __table_args__ = (UniqueConstraint("submitter_id", "client_request_id", name="uq_demand_create"),
                     Index("ix_demand_owner_status", "submitter_id", "status"),
                     Index("ix_demand_type_status", "demand_type_code", "status"),
                     Index("ix_demand_submitted", "submitted_at"), {"comment": "草稿与正式需求"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_no: Mapped[str | None] = mapped_column(String(40), unique=True)
    title: Mapped[str | None] = mapped_column(String(256))
    demand_type_code: Mapped[str | None] = mapped_column(String(32))
    subtype_code: Mapped[str | None] = mapped_column(String(32))
    content: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[str] = mapped_column(String(16), default="NORMAL", server_default="NORMAL")
    expect_delivery_at: Mapped[date | None] = mapped_column(Date)
    ext: Mapped[dict] = mapped_column(JSON, default=dict)
    quality: Mapped[list | None] = mapped_column(JSON)
    field_sources: Mapped[dict] = mapped_column(JSON, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    client_request_id: Mapped[str] = mapped_column(String(64))
    create_request_hash: Mapped[str] = mapped_column(String(64))
    standard_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_version.id"))
    quality_content_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", server_default="DRAFT")
    submitter_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    submitter_name: Mapped[str | None] = mapped_column(String(64))
    submitter_dept: Mapped[str | None] = mapped_column(String(128))
    channel: Mapped[str | None] = mapped_column(String(32))
    session_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    closed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    close_reason: Mapped[str | None] = mapped_column(String(256))


class DemandNoSeq(Base):
    __tablename__ = "demand_no_seq"
    __table_args__ = {"comment": "按类型按日编号流水"}
    biz_date: Mapped[date] = mapped_column(Date, primary_key=True)
    type_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class AgentSession(Timestamps, Base):
    __tablename__ = "agent_session"
    __table_args__ = {"comment": "每份草稿唯一启发会话"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_no: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    scene: Mapped[str] = mapped_column(String(32), default="SUBMIT_GUIDE")
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"), unique=True)
    title: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    asked_target: Mapped[str | None] = mapped_column(String(64))


class AgentMessage(Base):
    __tablename__ = "agent_message"
    __table_args__ = (UniqueConstraint("session_id", "request_id", "role", name="uq_message_request_role"),
                     {"comment": "Agent 消息与幂等响应"})
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("agent_session.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    structured_payload: Mapped[dict | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(64))
    request_hash: Mapped[str | None] = mapped_column(String(64))
    prompt_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_version.id"))
    model: Mapped[str | None] = mapped_column(String(64))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)"))
