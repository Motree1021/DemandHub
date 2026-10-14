"""通知中心：状态机钩子同事务写信箱 + 模板渲染 + 偏好 + 接收人解析 + 信箱服务。

白话：业务事件一旦发生，就给相关人信箱里放一封信（站内通知），写入即视为送达。
- 18 事件→7 类映射照蓝本 DemandEventConsumer.EVENT_NOTIFY_TYPE，模板编码=事件名
- 模板变量 ${var} 占位（蓝本 TemplateService 正则口径），未提供的变量→空串
- 接收人解析照蓝本 RecipientResolver；一期简化 org 不过滤，经理/管理者 = 静态 role ∪ 有效授权
  （决策③：grant 有 type_scope 按类型过滤、无 grant 默认全类型，EXECUTIVE/ADMIN 直通）
- 偏好：notification_preference 无记录=默认开；TODO 待办提醒不可关闭（蓝本 isClosable）
- 去重：事件通知与状态机同事务（回滚即不重发），不另设防重（蓝本一期口径）；
  SLA 扫描走 notify_dedupe（见 p4-sla）
- 出站：一期只写 IN_APP 行（send_status=SENT 写入即送达）；企微发送照 MockWecomMessageClient 仅记日志
"""

import logging
import re
from typing import Any, Iterable

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.db.models import (
    Demand,
    DemandRoleGrant,
    Notification,
    NotificationPreference,
    NotificationTemplate,
    User,
    now,
)

logger = logging.getLogger(__name__)

# ---- 7 类通知（蓝本 NotifyTypes）：TODO 待办提醒不可关闭，MENTION 保留无事件 ----
NOTIFY_TYPES = ("TODO", "STATUS_CHANGE", "ASSIGN", "REVIEW_REQUEST",
                "ACCEPTANCE_REQUEST", "SLA_ALERT", "MENTION")
NOT_CLOSABLE = {"TODO"}

# ---- 18 事件→7 类（蓝本 EVENT_NOTIFY_TYPE；RETURN_POOL/SPLIT 无通知） ----
EVENT_NOTIFY_TYPE = {
    "SUBMIT": "TODO", "RETURN": "TODO", "REVIEW_REJECT": "TODO", "ACCEPT_REJECT": "TODO",
    "WITHDRAW": "STATUS_CHANGE", "ACCEPT": "STATUS_CHANGE", "CLOSE": "STATUS_CHANGE",
    "CLAIM": "STATUS_CHANGE", "REVIEW_PASS": "STATUS_CHANGE", "START": "STATUS_CHANGE",
    "ACCEPT_PASS": "STATUS_CHANGE", "CHANGE_TYPE": "STATUS_CHANGE",
    "HOLD": "STATUS_CHANGE", "RESUME": "STATUS_CHANGE",
    "ASSIGN": "ASSIGN",
    "SUBMIT_REVIEW": "REVIEW_REQUEST",
    "SUBMIT_ACCEPTANCE": "ACCEPTANCE_REQUEST",
    "SLA_ALERT": "SLA_ALERT",
}

_VAR_PATTERN = re.compile(r"\$\{([a-zA-Z0-9_]+)\}")


def is_closable(notify_type: str) -> bool:
    return notify_type not in NOT_CLOSABLE


def render(template: str | None, variables: dict[str, Any]) -> str:
    """${var} 占位替换（蓝本 TemplateService）：未提供的变量→空串。"""
    if not template:
        return ""
    return _VAR_PATTERN.sub(lambda m: str(variables.get(m.group(1), "")), template)


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def build_vars(
    demand: Demand, operator: User | None, from_status: str | None, to_status: str | None,
    comment: str | None, extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """模板变量：基础位 + extra（camelCase→snake_case，蓝本 buildVars 口径）。

    决策④：from_status/to_status 保持状态码原样，不翻译。
    """
    variables: dict[str, Any] = {
        "demand_no": demand.demand_no or str(demand.id),
        "title": demand.title or "",
        "operator_name": operator.name if operator else "",
        "from_status": from_status or "",
        "to_status": to_status or "",
        "comment": comment or "",
    }
    for key, value in (extra or {}).items():
        variables[_snake(key)] = "" if value is None else value
    return variables


# ---- 接收人解析（蓝本 RecipientResolver；一期 org 不过滤） ----

async def _role_user_ids(
    db: AsyncSession, role_code: str, demand_type: str | None, *, scope_filtered: bool,
) -> set[int]:
    """某角色的接收人集合 = 静态 role（ACTIVE）∪ 生效授权。

    scope_filtered=True（MANAGER/HANDLER 类）：授权行 demand_type_scope 为空=全类型，
    否则按逗号串覆盖过滤（决策③）；False（EXECUTIVE/ADMIN 直通）：授权不看范围。
    """
    ids = set((await db.execute(
        select(User.id).where(User.role == role_code, User.status == "ACTIVE")
    )).scalars().all())
    current = now()
    rows = (await db.execute(
        select(DemandRoleGrant.user_id, DemandRoleGrant.demand_type_scope)
        .join(User, User.id == DemandRoleGrant.user_id)
        .where(DemandRoleGrant.role_code == role_code,
               DemandRoleGrant.is_deleted == 0,
               User.status == "ACTIVE",
               or_(DemandRoleGrant.effective_from.is_(None), DemandRoleGrant.effective_from <= current),
               or_(DemandRoleGrant.effective_to.is_(None), DemandRoleGrant.effective_to >= current))
    )).all()
    for user_id, type_scope in rows:
        if scope_filtered and type_scope:
            if demand_type and demand_type in {s.strip() for s in type_scope.split(",") if s.strip()}:
                ids.add(user_id)
        else:
            ids.add(user_id)
    return ids


async def _managers_or_executives(db: AsyncSession, demand_type: str | None) -> set[int]:
    """承接经理（无人兜底 EXECUTIVE，蓝本 managersOrExecutives 口径）。"""
    managers = await _role_user_ids(db, "MANAGER", demand_type, scope_filtered=True)
    if managers:
        return managers
    return await _role_user_ids(db, "EXECUTIVE", demand_type, scope_filtered=False)


async def resolve_recipients(
    db: AsyncSession, event: str, demand: Demand, extra: dict[str, Any] | None,
) -> list[int]:
    """按事件解析接收人（蓝本 RecipientResolver.switch 口径；操作人本人由调用方剔除）。"""
    assignee = demand.assignee_id
    if event in ("SUBMIT", "SUBMIT_REVIEW", "CHANGE_TYPE"):
        return list(await _managers_or_executives(db, demand.demand_type_code))
    if event in ("ACCEPT", "RETURN", "CLOSE", "CLAIM", "START", "SUBMIT_ACCEPTANCE"):
        return [demand.submitter_id]
    if event == "ASSIGN":
        assigned = (extra or {}).get("assigneeId") or assignee
        return [assigned] if assigned else []
    if event in ("REVIEW_PASS", "REVIEW_REJECT", "ACCEPT_REJECT"):
        return [assignee] if assignee else []
    if event == "ACCEPT_PASS":
        recipients = [assignee] if assignee else []
        recipients.extend(uid for uid in await _managers_or_executives(db, demand.demand_type_code)
                          if uid not in recipients)
        return recipients
    if event in ("HOLD", "RESUME"):
        return [uid for uid in (demand.submitter_id, assignee) if uid]
    if event == "SLA_ALERT":
        recipients = [assignee] if assignee else []
        managers = await _role_user_ids(db, "MANAGER", demand.demand_type_code, scope_filtered=True)
        executives = await _role_user_ids(db, "EXECUTIVE", demand.demand_type_code, scope_filtered=False)
        for uid in managers | executives:
            if uid not in recipients:
                recipients.append(uid)
        return recipients
    return []


# ---- 偏好 ----

async def _disabled_receivers(
    db: AsyncSession, notify_type: str, receiver_ids: Iterable[int],
) -> set[int]:
    """接收人中显式关闭该类的用户（无记录=默认开）。"""
    ids = list(receiver_ids)
    if not ids or not is_closable(notify_type):
        return set()
    return set((await db.execute(
        select(NotificationPreference.user_id).where(
            NotificationPreference.user_id.in_(ids),
            NotificationPreference.notify_type == notify_type,
            NotificationPreference.enabled.is_(False),
        )
    )).scalars().all())


async def get_preferences(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    """7 类全量返回；未存=默认开；TODO 恒开且不可关。"""
    rows = (await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user.id)
    )).scalars().all()
    stored = {row.notify_type: row.enabled for row in rows}
    return [
        {"notifyType": t, "closable": is_closable(t),
         "enabled": True if t in NOT_CLOSABLE else stored.get(t, True)}
        for t in NOTIFY_TYPES
    ]


async def set_preference(db: AsyncSession, user: User, notify_type: str, enabled: bool) -> None:
    if notify_type not in NOTIFY_TYPES:
        raise BizError(ErrorCode.PARAM_INVALID, f"通知类型仅允许 {'/'.join(NOTIFY_TYPES)}")
    if not is_closable(notify_type) and not enabled:
        raise BizError(ErrorCode.BIZ_ERROR, "TODO 待办提醒不可关闭")
    row = (await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.notify_type == notify_type,
        )
    )).scalar_one_or_none()
    if row is None:
        db.add(NotificationPreference(user_id=user.id, notify_type=notify_type, enabled=enabled))
    else:
        row.enabled = enabled
        row.updated_at = now()
    await db.flush()


# ---- 写信箱（状态机钩子，同事务） ----

async def _mock_wecom_send(receiver_id: int, title: str) -> None:
    """企微出站（照蓝本 MockWecomMessageClient）：一期仅记日志，不写 WECOM 行。"""
    logger.info("[MockWecomMessageClient] sendText to user=%s title=%s", receiver_id, title)


async def notify_transition(
    db: AsyncSession, *, demand: Demand, event: str, from_status: str | None,
    to_status: str | None, operator: User | None, comment: str | None,
    extra: dict[str, Any] | None,
) -> int:
    """事件通知主入口：映射类别 → 取模板 → 解析接收人（剔除操作人）→ 偏好过滤 → 写 IN_APP 行。

    模板缺失/停用：记告警跳过（不影响主流程）；返回写入条数。
    """
    notify_type = EVENT_NOTIFY_TYPE.get(event)
    if notify_type is None:
        return 0
    template = (await db.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.template_code == event,
            NotificationTemplate.status == "ACTIVE",
        )
    )).scalar_one_or_none()
    if template is None:
        logger.warning("通知模板缺失或停用，跳过事件通知: template_code=%s", event)
        return 0

    operator_id = operator.id if operator else None
    recipients = [uid for uid in dict.fromkeys(await resolve_recipients(db, event, demand, extra))
                  if uid and uid != operator_id]
    disabled = await _disabled_receivers(db, notify_type, recipients)
    variables = build_vars(demand, operator, from_status, to_status, comment, extra)
    title = render(template.title_template, variables)
    content = render(template.content_template, variables)
    written = 0
    for receiver_id in recipients:
        if receiver_id in disabled:
            continue
        db.add(Notification(
            demand_id=demand.id, receiver_id=receiver_id, channel="IN_APP",
            template_code=event, title=title, content=content,
            link=f"/demands/{demand.id}", is_read=False,
            send_status="SENT", sent_at=now(),
        ))
        await _mock_wecom_send(receiver_id, title)
        written += 1
    if written:
        await db.flush()
    return written


# ---- 信箱 ----

def serialize_notification(row: Notification) -> dict[str, Any]:
    return {
        "id": row.id,
        "demandId": row.demand_id,
        "templateCode": row.template_code,
        "notifyType": EVENT_NOTIFY_TYPE.get(row.template_code or "", None),
        "title": row.title,
        "content": row.content,
        "link": row.link,
        "isRead": row.is_read,
        "readAt": encode(row.read_at),
        "createdAt": encode(row.created_at),
    }


async def page_mine(
    db: AsyncSession, user: User, *, current: int, size: int, is_read: bool | None,
) -> dict[str, Any]:
    filters = [Notification.receiver_id == user.id, Notification.channel == "IN_APP"]
    if is_read is not None:
        filters.append(Notification.is_read.is_(is_read))
    total = (await db.execute(
        select(func.count(Notification.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(Notification).where(*filters)
        .order_by(Notification.id.desc())
        .offset((current - 1) * size).limit(size)
    )).scalars().all()
    return {"records": [serialize_notification(row) for row in rows], "total": total,
            "size": size, "current": current, "pages": (total + size - 1) // size}


async def unread_count(db: AsyncSession, user: User) -> int:
    return (await db.execute(
        select(func.count(Notification.id)).where(
            Notification.receiver_id == user.id,
            Notification.channel == "IN_APP",
            Notification.is_read.is_(False),
        )
    )).scalar_one()


async def mark_read(db: AsyncSession, user: User, notification_id: int) -> int:
    """单条已读：仅本人信箱；已读过的幂等返回 0。"""
    result = await db.execute(
        update(Notification).where(
            Notification.id == notification_id,
            Notification.receiver_id == user.id,
            Notification.is_read.is_(False),
        ).values(is_read=True, read_at=now())
    )
    return result.rowcount


async def mark_all_read(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        update(Notification).where(
            Notification.receiver_id == user.id,
            Notification.channel == "IN_APP",
            Notification.is_read.is_(False),
        ).values(is_read=True, read_at=now())
    )
    return result.rowcount


# ---- 模板管理（ADMIN） ----

def serialize_template(row: NotificationTemplate) -> dict[str, Any]:
    return {
        "id": row.id,
        "templateCode": row.template_code,
        "templateName": row.template_name,
        "titleTemplate": row.title_template,
        "contentTemplate": row.content_template,
        "status": row.status,
        "remark": row.remark,
        "createdAt": encode(row.created_at),
        "updatedAt": encode(row.updated_at),
    }


async def list_templates(db: AsyncSession) -> list[dict[str, Any]]:
    rows = (await db.execute(
        select(NotificationTemplate).order_by(NotificationTemplate.id)
    )).scalars().all()
    return [serialize_template(row) for row in rows]


async def create_template(
    db: AsyncSession, *, template_code: str, template_name: str,
    title_template: str, content_template: str, remark: str | None,
) -> NotificationTemplate:
    exists = (await db.execute(
        select(func.count(NotificationTemplate.id)).where(
            NotificationTemplate.template_code == template_code)
    )).scalar_one()
    if exists:
        raise BizError(ErrorCode.CONFLICT, "模板编码已存在")
    row = NotificationTemplate(
        template_code=template_code, template_name=template_name,
        title_template=title_template, content_template=content_template, remark=remark)
    db.add(row)
    await db.flush()
    return row


async def update_template(
    db: AsyncSession, template_id: int, *, template_name: str | None,
    title_template: str | None, content_template: str | None,
    status: str | None, remark: str | None,
) -> NotificationTemplate:
    row = await db.get(NotificationTemplate, template_id)
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "模板不存在")
    if status is not None and status not in ("ACTIVE", "INACTIVE"):
        raise BizError(ErrorCode.PARAM_INVALID, "状态仅允许 ACTIVE/INACTIVE")
    for field, value in (("template_name", template_name), ("title_template", title_template),
                         ("content_template", content_template), ("status", status),
                         ("remark", remark)):
        if value is not None:
            setattr(row, field, value)
    row.updated_at = now()
    await db.flush()
    return row


async def delete_template(db: AsyncSession, template_id: int) -> None:
    row = await db.get(NotificationTemplate, template_id)
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "模板不存在")
    await db.delete(row)
    await db.flush()


async def preview_template(
    db: AsyncSession, *, template_code: str | None,
    title_template: str | None, content_template: str | None, variables: dict[str, Any],
) -> dict[str, str]:
    """模板试渲染：给 templateCode 用库内模板（可被入参覆盖），否则直接用入参模板串。"""
    title_raw, content_raw = title_template, content_template
    if template_code:
        row = (await db.execute(
            select(NotificationTemplate).where(NotificationTemplate.template_code == template_code)
        )).scalar_one_or_none()
        if row is None:
            raise BizError(ErrorCode.NOT_FOUND, "模板不存在")
        title_raw = title_raw if title_raw is not None else row.title_template
        content_raw = content_raw if content_raw is not None else row.content_template
    return {"title": render(title_raw, variables), "content": render(content_raw, variables)}
