"""需求流转服务：start/hold/resume/submit-acceptance/acceptance-review/split/return-pool + 可见性与可用操作。

全部状态变更经状态机引擎（core.statemachine.transition），每次流转同事务写 transition_log（硬约束）。
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import is_admin
from app.core.errors import BizError, ErrorCode
from app.core.statemachine import engine
from app.db.models import (
    Assignment,
    Demand,
    DemandAttachment,
    DemandChangeLog,
    DemandRelation,
    EffortLog,
    Review,
    Solution,
    User,
    now,
)

# 管理视角可见的状态（DRAFT/NEED_INFO 为提报人私有编辑态）
FLOW_STATUSES = {"SUBMITTED", "TRIAGE", "ANALYZING", "SOLUTION_REVIEW", "CONFIRMED",
                 "IN_PROGRESS", "ACCEPTANCE", "DONE", "CLOSED"}
# 允许执行拆分的状态（已受理后的在途态）
SPLIT_ALLOWED_STATUSES = {"TRIAGE", "ANALYZING", "SOLUTION_REVIEW", "CONFIRMED", "IN_PROGRESS"}


def can_view_demand(
    user: User, demand: Demand, roles: frozenset[str] | set[str] | None = None,
) -> bool:
    """统一可见性：ADMIN 全量；提报人看本人；HANDLER/MANAGER/EXECUTIVE 可见已进入流转的需求。"""
    if is_admin(user) or demand.submitter_id == user.id:
        return True
    effective = roles if roles is not None else {user.role}
    return bool(effective & {"HANDLER", "MANAGER", "EXECUTIVE"}) and demand.status in FLOW_STATUSES


async def get_viewable(db: AsyncSession, user: User, demand_id: int) -> Demand:
    from app.services import role_service

    demand = await db.get(Demand, demand_id)
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    roles = await role_service.effective_roles(db, user)
    if not can_view_demand(user, demand, roles):
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    return demand


def require_assignee(user: User, demand: Demand, message: str = "仅当前处理人可操作"):
    if demand.assignee_id != user.id:
        raise BizError(ErrorCode.FORBIDDEN, message)


def require_assignee_or_privileged(
    user: User, demand: Demand, roles: frozenset[str] | set[str], message: str,
) -> None:
    """归属校验：当前处理人本人，或经理族（MANAGER 代办）/ ADMIN。"""
    from app.services.role_service import is_manager_like

    if demand.assignee_id != user.id and not is_manager_like(roles) and not is_admin(user):
        raise BizError(ErrorCode.FORBIDDEN, message)


def available_actions(
    demand: Demand, user: User, roles: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """当前用户对该需求可执行的事件：状态机规则 × 角色 × 业务归属（前端按钮显隐唯一依据）。"""
    from app.services.role_service import is_manager_like

    effective = roles if roles is not None else {user.role}
    privileged = is_manager_like(effective) or is_admin(user)
    actions = []
    for event in engine.available_events(demand, user, operator_roles=effective):
        if event in ("SUBMIT", "WITHDRAW", "ACCEPT_PASS", "ACCEPT_REJECT"):
            if demand.submitter_id == user.id:
                actions.append(event)
        elif event in ("START", "SUBMIT_ACCEPTANCE"):
            if demand.assignee_id == user.id:
                actions.append(event)
        elif event in ("HOLD", "RESUME", "RETURN_POOL", "SUBMIT_REVIEW"):
            # 经理可代办处理动作（蓝本口径：HANDLER_OR_MANAGER 由业务层放行）
            if demand.assignee_id == user.id or privileged:
                actions.append(event)
        else:
            # ACCEPT/RETURN/CLOSE/ASSIGN/CHANGE_TYPE/CLAIM/REVIEW_PASS/REVIEW_REJECT：
            # 状态机角色校验已通过即可（MANAGER/EXECUTIVE 或 HANDLER 领取）
            actions.append(event)
    # SPLIT 非状态机事件（父状态不变）：受理后在途 + 处理人/管理员 + 存在待实例化拆分
    if (demand.status in SPLIT_ALLOWED_STATUSES and not engine.is_held(demand)
            and (demand.assignee_id == user.id or is_admin(user))
            and (demand.ext or {}).get("pendingSplits")):
        actions.append("SPLIT")
    return actions


async def flow_detail(db: AsyncSession, user: User, demand_id: int) -> dict:
    """状态时间线 + 当前可用操作（管理后台按钮区与 H5 时间线共用）。"""
    from app.services import role_service

    demand = await get_viewable(db, user, demand_id)
    logs = await engine.list_logs(db, demand.id)
    roles = await role_service.effective_roles(db, user)
    return {
        "transitions": [engine.serialize_log(log) for log in logs],
        "availableActions": engine.events_label_map(available_actions(demand, user, roles)),
    }


# ---- 流转动作 ----

async def start(db: AsyncSession, user: User, demand_id: int) -> Demand:
    demand = await get_viewable(db, user, demand_id)
    require_assignee(user, demand)
    await engine.transition(db, demand_id, "START", user)
    return demand


async def hold(db: AsyncSession, user: User, demand_id: int, reason: str):
    if not reason or not reason.strip():
        raise BizError(ErrorCode.PARAM_INVALID, "挂起原因必填")
    from app.services import role_service

    demand = await get_viewable(db, user, demand_id)
    roles = await role_service.effective_roles(db, user)
    require_assignee_or_privileged(user, demand, roles, "仅当前处理人或经理/管理员可挂起")
    await engine.transition(db, demand_id, "HOLD", user, comment=reason.strip())
    return demand


async def resume(db: AsyncSession, user: User, demand_id: int) -> Demand:
    from app.services import role_service

    demand = await get_viewable(db, user, demand_id)
    roles = await role_service.effective_roles(db, user)
    require_assignee_or_privileged(user, demand, roles, "仅当前处理人或经理/管理员可恢复")
    await engine.transition(db, demand_id, "RESUME", user, comment="恢复处理")
    return demand


async def return_pool(db: AsyncSession, user: User, demand_id: int, reason: str) -> Demand:
    """退回处理池：ANALYZING → TRIAGE，清空处理人；处理人退单或经理/管理员收回。"""
    if not reason or not reason.strip():
        raise BizError(ErrorCode.PARAM_INVALID, "退回原因必填")
    from app.services import role_service

    demand = await get_viewable(db, user, demand_id)
    roles = await role_service.effective_roles(db, user)
    require_assignee_or_privileged(user, demand, roles, "仅当前处理人可退单或经理/管理员可收回")
    old_assignee = demand.assignee_id
    await engine.transition(
        db, demand_id, "RETURN_POOL", user,
        comment=reason.strip(), field_update={"assignee_id": None},
    )
    db.add(Assignment(
        demand_id=demand.id, from_user_id=old_assignee, to_user_id=None,
        action="RETURN", operator_id=user.id,
    ))
    return demand


async def submit_acceptance(db: AsyncSession, user: User, demand_id: int) -> Demand:
    demand = await get_viewable(db, user, demand_id)
    require_assignee(user, demand, "仅当前处理人可提交验收")
    # 前置三校验（蓝本口径）：方案已确认 + 工时已填报 + 交付物已上传
    missing = []
    approved = (await db.execute(select(func.count(Solution.id)).where(
        Solution.demand_id == demand_id, Solution.status == "APPROVED"))).scalar_one()
    if approved == 0:
        missing.append("方案未确认")
    efforts = (await db.execute(select(func.count(EffortLog.id)).where(
        EffortLog.demand_id == demand_id))).scalar_one()
    if efforts == 0:
        missing.append("工时未填报")
    attachments = (await db.execute(select(func.count(DemandAttachment.id)).where(
        DemandAttachment.demand_id == demand_id,
        DemandAttachment.biz_type == "DEMAND",
        DemandAttachment.status == "ACTIVE"))).scalar_one()
    if attachments == 0:
        missing.append("交付物未上传")
    if missing:
        raise BizError(ErrorCode.ACCEPTANCE_PRECONDITION, "、".join(missing))
    await engine.transition(db, demand_id, "SUBMIT_ACCEPTANCE", user)
    return demand


def _validate_score(value: int | None, label: str) -> int:
    if value is None or not 1 <= value <= 5:
        raise BizError(ErrorCode.PARAM_INVALID, f"验收通过需填写 1-5 星{label}")
    return value


async def acceptance_review(
    db: AsyncSession, user: User, demand_id: int, *,
    result: str, quality_score: int | None, satisfaction_score: int | None, opinion: str | None,
) -> Demand:
    """提报人验收：PASS → DONE（评分必填）/ REJECT → IN_PROGRESS（意见必填）；写 review 留痕。"""
    if result not in {"PASS", "REJECT"}:
        raise BizError(ErrorCode.PARAM_INVALID, "验收结论必须为 PASS 或 REJECT")
    demand = await get_viewable(db, user, demand_id)
    if demand.submitter_id != user.id:
        raise BizError(ErrorCode.FORBIDDEN, "仅提报人可验收")
    if result == "PASS":
        quality_score = _validate_score(quality_score, "质量评分")
        satisfaction_score = _validate_score(satisfaction_score, "满意度评分")
        await engine.transition(db, demand_id, "ACCEPT_PASS", user, comment=opinion, field_update={
            "quality_score": quality_score, "satisfaction_score": satisfaction_score,
            "done_at": now(),
        })
    else:
        if not opinion or not opinion.strip():
            raise BizError(ErrorCode.PARAM_INVALID, "验收打回意见必填")
        opinion = opinion.strip()
        await engine.transition(db, demand_id, "ACCEPT_REJECT", user, comment=opinion)
    db.add(Review(
        demand_id=demand.id, review_type="ACCEPTANCE", target_id=None, result=result,
        opinion=opinion, quality_score=quality_score if result == "PASS" else None,
        satisfaction_score=satisfaction_score if result == "PASS" else None,
        reviewer_id=user.id,
    ))
    await db.flush()
    return demand


async def split(
    db: AsyncSession, user: User, demand_id: int, items: list[dict] | None,
) -> list[Demand]:
    """拆分实例化：消费 ext.pendingSplits（或显式 items），生成 TRIAGE 态子需求并写关系与日志。"""
    from app.services.demand_no import next_no

    parent = await get_viewable(db, user, demand_id)
    if parent.status not in SPLIT_ALLOWED_STATUSES:
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅受理后的在途需求可拆分")
    if engine.is_held(parent):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "挂起中的需求不可拆分")
    if parent.assignee_id != user.id and not is_admin(user):
        raise BizError(ErrorCode.FORBIDDEN, "仅当前处理人或管理员可拆分")

    pending = (parent.ext or {}).get("pendingSplits") or []
    raw_items = items if items is not None else pending
    if not raw_items:
        raise BizError(ErrorCode.PARAM_INVALID, "没有可实例化的拆分项")

    group_id = parent.split_group_id or uuid.uuid4().hex
    # P5 组织回填（蓝本口径）：子需求提报人组织按操作人解析，承接组织继承父需求
    from app.services import org_service
    operator_org_id = await org_service.resolve_user_org_id(db, user)
    children: list[Demand] = []
    for item in raw_items:
        title = (item.get("title") or "").strip()[:128]
        summary = (item.get("summary") or "").strip()
        if not title:
            raise BizError(ErrorCode.PARAM_INVALID, "拆分项标题必填")
        child = Demand(
            demand_no=await next_no(db, parent.demand_type_code, now().date()),
            title=title, content=summary or title,
            demand_type_code=parent.demand_type_code,
            urgency=parent.urgency,
            status="TRIAGE",  # 直接入处理池（蓝本口径：父需求已受理，子需求随父承接）
            submitter_id=user.id, submitter_name=user.name, submitter_dept=user.dept_name,
            submitted_at=now(),
            channel=parent.channel,
            split_from_id=parent.id, split_group_id=group_id,
            client_request_id=f"split-{uuid.uuid4().hex}",
            create_request_hash="split",
            standard_version_id=parent.standard_version_id,
            submitter_org_id=operator_org_id,
            assignee_org_id=parent.assignee_org_id,
        )
        db.add(child)
        await db.flush()
        db.add(DemandRelation(from_id=parent.id, to_id=child.id, type="SPLIT"))
        await engine.write_transition_log(
            db, child, "SPLIT", user, from_status=None, to_status="TRIAGE",
            comment=f"由需求 {parent.demand_no} 拆分创建",
            extra={"parentDemandId": parent.id, "parentDemandNo": parent.demand_no},
        )
        children.append(child)

    # 父需求：回填组号 + 清掉已消费的 pendingSplits 并留痕
    parent.split_group_id = group_id
    if pending:
        ext = dict(parent.ext or {})
        ext.pop("pendingSplits", None)
        parent.ext = ext
        db.add(DemandChangeLog(
            demand_id=parent.id, field_key="ext.pendingSplits",
            old_value=pending, new_value=None, source="user",
        ))
    parent.updated_at = now()
    await db.flush()
    return children
