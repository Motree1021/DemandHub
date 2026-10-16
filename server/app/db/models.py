from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
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
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, onupdate=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


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
    channel: Mapped[str] = mapped_column(
        String(32), default="CHUANGJIN_LS", server_default="CHUANGJIN_LS"
    )
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    last_login_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    # P1 账密与角色：账密用户无企微身份，wecom_userid 落占位值 acct:<login_account>
    login_account: Mapped[str | None] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(128))
    must_change_pwd: Mapped[bool] = mapped_column(default=False, server_default="0")
    fail_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    role: Mapped[str] = mapped_column(String(16), default="REPORTER", server_default="REPORTER")
    # 需求类型权限（2026-10-16 拍板）：逗号分隔类型码，NULL=无权限；仅业务角色生效，ADMIN/REPORTER 不受限
    type_scope: Mapped[str | None] = mapped_column(String(64))


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    __table_args__ = {"comment": "续期凭证：旋转使用，旧票即时吊销"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("dh_user.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3))
    revoked: Mapped[bool] = mapped_column(default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class PromptVersion(Base):
    __tablename__ = "prompt_version"
    __table_args__ = {"comment": "不可变标准与提示词快照"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(32))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class Demand(Timestamps, Base):
    __tablename__ = "demand"
    __table_args__ = (
        UniqueConstraint("submitter_id", "client_request_id", name="uq_demand_create"),
        Index("ix_demand_owner_status", "submitter_id", "status"),
        Index("ix_demand_type_status", "demand_type_code", "status"),
        Index("ix_demand_submitted", "submitted_at"),
        Index("ix_demand_split_group", "split_group_id"),
        Index("ix_demand_split_from", "split_from_id"),
        {"comment": "草稿与正式需求"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_no: Mapped[str | None] = mapped_column(String(40), unique=True)
    title: Mapped[str | None] = mapped_column(String(256))
    demand_type_code: Mapped[str | None] = mapped_column(String(32))
    subtype_code: Mapped[str | None] = mapped_column(String(32))
    content: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[str | None] = mapped_column(String(16))
    expect_delivery_at: Mapped[date | None] = mapped_column(Date)
    ext: Mapped[dict] = mapped_column(JSON, default=dict)
    elements: Mapped[dict | None] = mapped_column(JSON)
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
    split_from_id: Mapped[int | None] = mapped_column(ForeignKey("demand.id"))
    split_group_id: Mapped[str | None] = mapped_column(String(36))
    submitted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    closed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    close_reason: Mapped[str | None] = mapped_column(String(256))
    # P2 流转列
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("dh_user.id"))
    hold_snapshot_status: Mapped[str | None] = mapped_column(String(32))
    hold_reason: Mapped[str | None] = mapped_column(String(256))
    confirmed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    done_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    quality_score: Mapped[int | None] = mapped_column(SmallInteger)
    satisfaction_score: Mapped[int | None] = mapped_column(SmallInteger)
    # P4 组织维度留口（一期只建不用：看板 Top10 走 submitter_dept 快照，org 过滤待 P5）
    assignee_org_id: Mapped[int | None] = mapped_column(BigInteger)
    submitter_org_id: Mapped[int | None] = mapped_column(BigInteger)


class DemandChangeLog(Base):
    __tablename__ = "demand_change_log"
    __table_args__ = (
        Index("ix_change_demand_time", "demand_id", "created_at"),
        {"comment": "需求要素变更留痕（E7）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id", name="fk_change_demand"))
    field_key: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    new_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(16), default="user", server_default="user")
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("dh_user.id", name="fk_change_user"))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class DemandNoSeq(Base):
    __tablename__ = "demand_no_seq"
    __table_args__ = {"comment": "按类型按日编号流水"}
    biz_date: Mapped[date] = mapped_column(Date, primary_key=True)
    type_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class DemandAttachment(Timestamps, Base):
    """需求附件（图片/文档）：本地目录存储，storage_key 不外泄，下载走鉴权接口。
    仅作为需求材料随需求一并流转，不做多模态识别。"""

    __tablename__ = "demand_attachment"
    __table_args__ = (
        Index("ix_attachment_demand_id", "demand_id", "id"),
        {"comment": "需求附件（图片/文档，随需求一并流转）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    file_name: Mapped[str] = mapped_column(String(256))
    kind: Mapped[str] = mapped_column(String(16), comment="附件类别：IMAGE/DOC")
    file_ext: Mapped[str] = mapped_column(
        String(16), comment="扩展名（小写，白名单校验后的安全值）"
    )
    size: Mapped[int] = mapped_column(Integer, comment="文件大小（字节）")
    storage_key: Mapped[str] = mapped_column(
        String(128), unique=True, comment="存储键（uuid，服务端目录内相对定位，不外泄）"
    )
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    status: Mapped[str] = mapped_column(
        String(16), default="ACTIVE", server_default="ACTIVE", comment="ACTIVE/DELETED（软删）"
    )
    # P2：附件归属扩展（DRAFT/DEMAND/SOLUTION/COMMENT），DEMAND 时 biz_id 同 demand_id
    biz_type: Mapped[str] = mapped_column(String(16), default="DEMAND", server_default="DEMAND")
    biz_id: Mapped[int | None] = mapped_column(BigInteger)


class AgentSession(Timestamps, Base):
    __tablename__ = "agent_session"
    __table_args__ = (
        # P3 起改为 (demand_id, scene) 复合唯一：一个需求可并存 SUBMIT_GUIDE 与 HANDLE_ASSIST 两类会话
        UniqueConstraint("demand_id", "scene", name="uk_agent_session_demand_scene"),
        {"comment": "提报启发（每草稿唯一）与处理辅助（每需求唯一）会话"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_no: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    scene: Mapped[str] = mapped_column(String(32), default="SUBMIT_GUIDE")
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    title: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    asked_target: Mapped[str | None] = mapped_column(String(64))


class AgentMessage(Base):
    __tablename__ = "agent_message"
    __table_args__ = (
        UniqueConstraint("session_id", "request_id", "role", name="uq_message_request_role"),
        {"comment": "Agent 消息与幂等响应"},
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class AgentDraft(Timestamps, Base):
    __tablename__ = "agent_draft"
    __table_args__ = (
        Index("idx_agent_draft_demand", "demand_id"),
        {"comment": "处理辅助 Agent 草稿区"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    session_id: Mapped[int] = mapped_column(ForeignKey("agent_session.id"))
    draft_type: Mapped[str] = mapped_column(String(16))  # QUESTIONS 调研问题 / SOLUTION 方案初稿
    content: Mapped[str] = mapped_column(Text)  # 草稿内容 JSON
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")  # PENDING/CONFIRMED/DISCARDED
    created_by: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    confirmed_by: Mapped[int | None] = mapped_column(BigInteger)
    confirmed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    target_solution_id: Mapped[int | None] = mapped_column(BigInteger)


class RagVector(Timestamps, Base):
    __tablename__ = "rag_vector"
    __table_args__ = (
        UniqueConstraint("demand_id", name="uk_rag_vector_demand"),  # 重复向量化幂等跳过
        Index("idx_rag_vector_status", "status"),
        {"comment": "RAG 需求向量知识库"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    demand_no: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(256))
    demand_type_code: Mapped[str | None] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)  # 向量化原文（标题+描述+最新方案+评审意见）
    embedding: Mapped[str] = mapped_column(Text)  # 向量 JSON 数组（L2 归一化）
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")  # ACTIVE/INACTIVE
    vectorized_at: Mapped[datetime] = mapped_column(DATETIME(fsp=3), default=now)


class StateMachineConfig(Timestamps, Base):
    __tablename__ = "state_machine_config"
    __table_args__ = {"comment": "状态机规则配置（热重载）"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(64), unique=True)
    config_name: Mapped[str] = mapped_column(String(128))
    config_json: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    remark: Mapped[str | None] = mapped_column(String(512))


class DemandTransitionLog(Base):
    __tablename__ = "demand_transition_log"
    __table_args__ = (
        Index("idx_transition_demand_time", "demand_id", "created_at"),
        {"comment": "需求状态流转日志（每次流转必写）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    event: Mapped[str] = mapped_column(String(64))
    operator_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    operator_snapshot: Mapped[str | None] = mapped_column(String(128))
    hold_flag: Mapped[bool] = mapped_column(default=False, server_default="0")
    comment: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class Assignment(Base):
    __tablename__ = "assignment"
    __table_args__ = (
        Index("idx_assignment_demand", "demand_id"),
        Index("idx_assignment_to", "to_user_id", "action"),
        {"comment": "需求分派领取记录"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    from_user_id: Mapped[int | None] = mapped_column(BigInteger)
    to_user_id: Mapped[int | None] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(16))  # ASSIGN/CLAIM/RETURN
    operator_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class Solution(Timestamps, Base):
    __tablename__ = "solution"
    __table_args__ = (
        UniqueConstraint("demand_id", "version", name="uk_solution_demand_version"),
        Index("idx_solution_demand", "demand_id"),
        {"comment": "需求方案"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    version: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    spec_content: Mapped[str | None] = mapped_column(Text)
    solution_content: Mapped[str | None] = mapped_column(Text)
    plan_delivery_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", server_default="DRAFT")
    remark: Mapped[str | None] = mapped_column(String(512))


class Review(Base):
    __tablename__ = "review"
    __table_args__ = (
        Index("idx_review_demand_type", "demand_id", "review_type"),
        {"comment": "方案与验收评审记录（留痕不可改）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    review_type: Mapped[str] = mapped_column(String(16))  # SOLUTION/ACCEPTANCE
    target_id: Mapped[int | None] = mapped_column(ForeignKey("solution.id"))
    result: Mapped[str] = mapped_column(String(16))  # PASS/REJECT
    opinion: Mapped[str | None] = mapped_column(Text)
    quality_score: Mapped[int | None] = mapped_column(SmallInteger)
    satisfaction_score: Mapped[int | None] = mapped_column(SmallInteger)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class Comment(Timestamps, Base):
    __tablename__ = "comment"
    __table_args__ = (
        Index("idx_comment_demand_time", "demand_id", "created_at"),
        {"comment": "需求评论（仅作者可改，不可删）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    author_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    content: Mapped[str] = mapped_column(Text)
    mentioned_user_ids: Mapped[str | None] = mapped_column(String(512))


class EffortLog(Timestamps, Base):
    __tablename__ = "effort_log"
    __table_args__ = (
        Index("idx_effort_demand", "demand_id"),
        Index("idx_effort_user_date", "user_id", "work_date"),
        {"comment": "需求工时记录"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    hours: Mapped[float] = mapped_column(Numeric(5, 1))
    work_date: Mapped[date] = mapped_column(Date)
    remark: Mapped[str | None] = mapped_column(String(512))


class DemandRelation(Base):
    __tablename__ = "demand_relation"
    __table_args__ = (
        UniqueConstraint("from_id", "to_id", "type", name="uk_relation_pair"),
        Index("idx_relation_to", "to_id"),
        {"comment": "需求关系（父子/依赖/重复/拆分）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    to_id: Mapped[int] = mapped_column(ForeignKey("demand.id"))
    type: Mapped[str] = mapped_column(String(16))  # PARENT/DEPENDS/DUPLICATE/SPLIT
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


# ==================== P4 通知与统计 ====================


class Notification(Base):
    """站内信信箱（一期只写 IN_APP 行，写入即送达；WECOM 渠道列保留二期）。"""
    __tablename__ = "notification"
    __table_args__ = (
        Index("idx_receiver_unread", "receiver_id", "is_read"),
        Index("idx_demand", "demand_id"),
        {"comment": "通知消息（信箱表，替代 MQ）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_id: Mapped[int | None] = mapped_column(BigInteger)
    receiver_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    channel: Mapped[str] = mapped_column(String(16), default="IN_APP", server_default="IN_APP")
    template_code: Mapped[str | None] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(512))
    is_read: Mapped[bool] = mapped_column(default=False, server_default="0")
    read_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    send_status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))


class NotificationTemplate(Timestamps, Base):
    __tablename__ = "notification_template"
    __table_args__ = {"comment": "通知模板"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_code: Mapped[str] = mapped_column(String(64), unique=True)
    template_name: Mapped[str] = mapped_column(String(128))
    title_template: Mapped[str] = mapped_column(String(256))
    content_template: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    remark: Mapped[str | None] = mapped_column(String(512))


class NotificationPreference(Timestamps, Base):
    """用户通知偏好（TODO 待办提醒不可关闭，不落库）。"""
    __tablename__ = "notification_preference"
    __table_args__ = (
        UniqueConstraint("user_id", "notify_type", name="uk_user_type"),
        {"comment": "用户通知偏好"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    notify_type: Mapped[str] = mapped_column(String(32))
    enabled: Mapped[bool] = mapped_column(default=True, server_default="1")


class NotifyDedupe(Base):
    """通知去重（替 Redis setIfAbsent + 7 天 TTL；事务回滚=下轮重试）。"""
    __tablename__ = "notify_dedupe"
    __table_args__ = {"comment": "通知去重（替 Redis）"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class SlaConfig(Timestamps, Base):
    __tablename__ = "sla_config"
    __table_args__ = (
        UniqueConstraint("demand_type_code", "status", name="uk_type_status"),
        {"comment": "SLA 停留时长配置（类型 × 状态）"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    demand_type_code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    warn_minutes: Mapped[int] = mapped_column(Integer)
    max_minutes: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(default=True, server_default="1")
    remark: Mapped[str | None] = mapped_column(String(512))


class DemandStatDaily(Base):
    """需求日统计预聚合（组织维度一期写 0，待组织域启用）。"""
    __tablename__ = "demand_stat_daily"
    __table_args__ = (
        UniqueConstraint("stat_date", "demand_type_code", "assignee_org_id", "reporter_org_id", "status",
                         name="uk_dim"),
        {"comment": "需求日统计预聚合"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stat_date: Mapped[date] = mapped_column(Date)
    demand_type_code: Mapped[str] = mapped_column(String(32))
    assignee_org_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    reporter_org_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(32))
    cnt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    avg_cycle_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, onupdate=now,
        server_default=text("CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)")
    )


class ReportExportTask(Base):
    """报表导出异步任务（file_path 落本地目录，替代 MinIO）。"""
    __tablename__ = "report_export_task"
    __table_args__ = (
        Index("idx_requester", "requester_id", "status"),
        {"comment": "报表导出异步任务"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(64), unique=True)
    report_type: Mapped[str] = mapped_column(String(32))
    params_json: Mapped[str | None] = mapped_column(Text)
    requester_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    status: Mapped[str] = mapped_column(String(16), default="PENDING", server_default="PENDING")
    file_path: Mapped[str | None] = mapped_column(String(512))
    file_name: Mapped[str | None] = mapped_column(String(256))
    error_msg: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))


class DemandRoleGrant(Timestamps, Base):
    """业务角色本地授权（EXECUTIVE/MANAGER；type_scope 逗号多选，NULL=全部类型）。"""
    __tablename__ = "demand_role_grant"
    __table_args__ = (
        UniqueConstraint("user_id", "role_code", "org_id", "demand_type_scope", "is_deleted",
                         name="uk_grant"),
        Index("idx_role", "role_code"),
        {"comment": "业务角色本地授权"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("dh_user.id"))
    role_code: Mapped[str] = mapped_column(String(32))
    org_id: Mapped[int | None] = mapped_column(BigInteger)
    demand_type_scope: Mapped[str | None] = mapped_column(String(256))
    effective_from: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    effective_to: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    granted_by: Mapped[int | None] = mapped_column(ForeignKey("dh_user.id"))
    is_deleted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class SysDict(Timestamps, Base):
    """业务字典（dict_type+item_code 唯一；编码不可改，仅名称/排序/状态可编辑）。"""
    __tablename__ = "sys_dict"
    __table_args__ = (
        UniqueConstraint("dict_type", "item_code", name="uk_dict"),
        {"comment": "业务字典"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    dict_type: Mapped[str] = mapped_column(String(64))
    item_code: Mapped[str] = mapped_column(String(64))
    item_name: Mapped[str] = mapped_column(String(128))
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")


class DemandType(Timestamps, Base):
    """需求类型注册（表管注册/启停/状态机绑定/排序；五区字段标准仍走 yaml 快照）。
    sla_config / parent_type_code 为蓝本预留列，一期透传不参与业务。"""
    __tablename__ = "demand_type"
    __table_args__ = (
        UniqueConstraint("type_code", name="uk_type_code"),
        {"comment": "需求类型"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    type_code: Mapped[str] = mapped_column(String(32))
    type_name: Mapped[str] = mapped_column(String(64))
    parent_type_code: Mapped[str | None] = mapped_column(String(32))
    default_org_id: Mapped[int | None] = mapped_column(BigInteger)
    state_machine_key: Mapped[str] = mapped_column(String(64), default="DEFAULT", server_default="DEFAULT")
    sla_config: Mapped[dict | None] = mapped_column(JSON)
    sort: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")


class DemandChannel(Timestamps, Base):
    """渠道注册（只做登记/启停；SSO 对接参数走 .env 不迁表，config_json 为蓝本预留列）。"""
    __tablename__ = "demand_channel"
    __table_args__ = (
        UniqueConstraint("channel_code", name="uk_channel_code"),
        {"comment": "需求来源渠道"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_code: Mapped[str] = mapped_column(String(32))
    channel_name: Mapped[str] = mapped_column(String(64))
    app_id: Mapped[str | None] = mapped_column(String(64))
    callback_enabled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")
    # 渠道白名单：开关默认关（全放行），拦截页联系引导随渠道行走公开接口
    whitelist_enabled: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    whitelist_contact: Mapped[str | None] = mapped_column(String(255))
    config_json: Mapped[dict | None] = mapped_column(JSON)


class DemandChannelWhitelist(Timestamps, Base):
    """渠道白名单（管「允许谁进」，与 dh_user 用户档案相互独立，登录命中才建档）。"""
    __tablename__ = "demand_channel_whitelist"
    __table_args__ = (
        UniqueConstraint("channel_code", "channel_user_id", name="uk_whitelist_user"),
        {"comment": "渠道白名单"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_code: Mapped[str] = mapped_column(String(32))
    channel_user_id: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ENABLED", server_default="ENABLED")
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_by_name: Mapped[str | None] = mapped_column(String(64))


class DemandChannelWhitelistLog(Base):
    """白名单操作留痕（增/删/启停/开关/文案；操作对象快照，行只增不改）。"""
    __tablename__ = "demand_channel_whitelist_log"
    __table_args__ = (
        Index("ix_whitelist_log_channel", "channel_code", "created_at"),
        {"comment": "渠道白名单操作留痕"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(24))
    channel_code: Mapped[str] = mapped_column(String(32))
    channel_user_id: Mapped[str | None] = mapped_column(String(64))
    operator_id: Mapped[int] = mapped_column(BigInteger)
    operator_name: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )


class DemandOrg(Timestamps, Base):
    """组织树（物化路径 /100/110/ 尾斜杠，子树 startsWith 匹配；
    external_dept_id 为渠道侧部门 ID，票据登录部门映射用，未命中挂虚拟组织 900）。"""
    __tablename__ = "demand_org"
    __table_args__ = (
        Index("idx_parent", "parent_id"),
        Index("idx_path", "path"),
        Index("idx_status", "status"),
        {"comment": "组织树"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    level: Mapped[str] = mapped_column(String(16))
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    path: Mapped[str] = mapped_column(String(512))
    org_kind: Mapped[str | None] = mapped_column(String(16))
    external_flag: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    external_dept_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", server_default="ACTIVE")


class ChannelDeptUnmapped(Base):
    """渠道部门未映射校准清单（登录部门映射未命中时 upsert 计数，管理员校准后删行）。"""
    __tablename__ = "channel_dept_unmapped"
    __table_args__ = (
        UniqueConstraint("channel_code", "dept_id", name="uk_channel_dept"),
        {"comment": "渠道部门未映射校准清单"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_code: Mapped[str] = mapped_column(String(32))
    dept_id: Mapped[str] = mapped_column(String(32))
    dept_name: Mapped[str | None] = mapped_column(String(128))
    dept_path: Mapped[str | None] = mapped_column(String(256))
    sample_channel_user_id: Mapped[str | None] = mapped_column(String(64))
    hit_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    first_seen_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), default=now, onupdate=now, server_default=text("CURRENT_TIMESTAMP(3)")
    )
