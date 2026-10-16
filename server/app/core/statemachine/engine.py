"""状态机引擎：规则落库（state_machine_config）+ 热重载 + 全部流转经此引擎并写 transition_log。

白话：状态机就是一张「规则表」——什么状态下、什么人、能触发哪个事件、事件后变成什么状态。
- 规则存数据库，改规则不重启（热重载 POST /admin/state-machines/reload）
- ON_HOLD 不是主状态：挂起 = demand.hold_snapshot_status 记下主状态并贴上"暂停"标签，
  主状态列不动；挂起中除 RESUME 外一切事件按非法流转拒绝；恢复撕掉标签回到原主状态
- ADMIN 直通：规则里的角色限制对 ADMIN 一律放行（蓝本口径）
- 硬约束：任何代码不得绕过本引擎直接 update demand.status
"""

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import Demand, DemandTransitionLog, StateMachineConfig, User, now

ON_HOLD = "ON_HOLD"
TERMINAL_STATUSES = {"DONE", "CLOSED"}
VALID_ROLES = {"ADMIN", "EXECUTIVE", "MANAGER", "HANDLER", "REPORTER"}

STATUS_LABELS = {
    "DRAFT": "草稿", "SUBMITTED": "待受理", "NEED_INFO": "待补充", "TRIAGE": "待分派/待领取",
    "ANALYZING": "分析中", "SOLUTION_REVIEW": "方案待评审", "CONFIRMED": "已确认/已排期",
    "IN_PROGRESS": "处理中", "ACCEPTANCE": "待验收", "DONE": "已完成", "CLOSED": "已关闭",
    ON_HOLD: "挂起",
}

EVENT_LABELS = {
    "SUBMIT": "提交", "WITHDRAW": "撤销", "ACCEPT": "受理", "RETURN": "退回补充",
    "CLOSE": "关闭", "ASSIGN": "分派", "CLAIM": "领取", "RETURN_POOL": "退回处理池",
    "CHANGE_TYPE": "类型修正", "SUBMIT_REVIEW": "提交方案评审", "REVIEW_PASS": "评审通过",
    "REVIEW_REJECT": "评审打回", "START": "开始处理", "SUBMIT_ACCEPTANCE": "提交验收",
    "ACCEPT_PASS": "验收通过", "ACCEPT_REJECT": "验收打回", "HOLD": "挂起", "RESUME": "恢复",
    "SPLIT": "拆分",
}


@dataclass(frozen=True)
class Rule:
    """一条流转规则：源态 + 事件 → 目标态；to 为 None 表示主状态不变（CHANGE_TYPE/挂起类）。"""

    from_status: str
    event: str
    to: str | None
    roles: frozenset[str]  # 空集 = 状态机不卡角色，归属由业务层校验
    remark: str = ""


# 代码内置兜底规则（与最新 alembic 种子一致；角色口径对齐蓝本 StateMachineConfig）：
# - 受理族（ACCEPT/RETURN/CLOSE/ASSIGN/REVIEW_PASS/REVIEW_REJECT）= MANAGER
# - 类型修正（CHANGE_TYPE）= EXECUTIVE；处理族（CLAIM/START/SUBMIT_ACCEPTANCE）= HANDLER
# - 处理人可代办族（SUBMIT_REVIEW/HOLD/RESUME/RETURN_POOL）= HANDLER + MANAGER
# - ADMIN 不写入规则：check_role 一律直通（蓝本"ADMIN 超级用户全线直通"口径）
# 表为空/配置不可用时引擎仍可用
DEFAULT_RULES: tuple[Rule, ...] = tuple(
    Rule(r["from"], r["event"], r["to"], frozenset(r["roles"]), r["remark"])
    for r in json.loads("""{"rules": [
        {"from": "DRAFT", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "提交需求"},
        {"from": "NEED_INFO", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "补充后重新提交"},
        {"from": "DRAFT", "event": "WITHDRAW", "to": "CLOSED", "roles": [], "remark": "撤销草稿"},
        {"from": "SUBMITTED", "event": "WITHDRAW", "to": "CLOSED", "roles": [], "remark": "提报人撤销"},
        {"from": "NEED_INFO", "event": "WITHDRAW", "to": "CLOSED", "roles": [], "remark": "待补充撤销"},
        {"from": "SUBMITTED", "event": "ACCEPT", "to": "TRIAGE", "roles": ["MANAGER"], "remark": "受理通过"},
        {"from": "SUBMITTED", "event": "RETURN", "to": "NEED_INFO", "roles": ["MANAGER"], "remark": "退回补充"},
        {"from": "SUBMITTED", "event": "CLOSE", "to": "CLOSED", "roles": ["MANAGER"], "remark": "不受理/重复关闭"},
        {"from": "TRIAGE", "event": "CLOSE", "to": "CLOSED", "roles": ["MANAGER"], "remark": "待分派关闭"},
        {"from": "TRIAGE", "event": "ASSIGN", "to": "ANALYZING", "roles": ["MANAGER"], "remark": "经理分派"},
        {"from": "TRIAGE", "event": "CLAIM", "to": "ANALYZING", "roles": ["HANDLER"], "remark": "处理人领取"},
        {"from": "ANALYZING", "event": "RETURN_POOL", "to": "TRIAGE", "roles": ["HANDLER", "MANAGER"], "remark": "退回处理池"},
        {"from": "ANALYZING", "event": "SUBMIT_REVIEW", "to": "SOLUTION_REVIEW", "roles": ["HANDLER", "MANAGER"], "remark": "提交方案评审"},
        {"from": "SOLUTION_REVIEW", "event": "REVIEW_PASS", "to": "CONFIRMED", "roles": ["MANAGER"], "remark": "评审通过"},
        {"from": "SOLUTION_REVIEW", "event": "REVIEW_REJECT", "to": "ANALYZING", "roles": ["MANAGER"], "remark": "评审打回"},
        {"from": "CONFIRMED", "event": "START", "to": "IN_PROGRESS", "roles": ["HANDLER"], "remark": "开始处理"},
        {"from": "IN_PROGRESS", "event": "SUBMIT_ACCEPTANCE", "to": "ACCEPTANCE", "roles": ["HANDLER"], "remark": "提交验收"},
        {"from": "ACCEPTANCE", "event": "ACCEPT_PASS", "to": "DONE", "roles": [], "remark": "验收通过"},
        {"from": "ACCEPTANCE", "event": "ACCEPT_REJECT", "to": "IN_PROGRESS", "roles": [], "remark": "验收打回"},
        {"from": "SUBMITTED", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "NEED_INFO", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "TRIAGE", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "ANALYZING", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "SOLUTION_REVIEW", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "CONFIRMED", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "IN_PROGRESS", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "ACCEPTANCE", "event": "CHANGE_TYPE", "to": null, "roles": ["EXECUTIVE"], "remark": "类型修正"},
        {"from": "ANALYZING", "event": "HOLD", "to": null, "roles": ["HANDLER", "MANAGER"], "remark": "挂起"},
        {"from": "SOLUTION_REVIEW", "event": "HOLD", "to": null, "roles": ["HANDLER", "MANAGER"], "remark": "挂起"},
        {"from": "CONFIRMED", "event": "HOLD", "to": null, "roles": ["HANDLER", "MANAGER"], "remark": "挂起"},
        {"from": "IN_PROGRESS", "event": "HOLD", "to": null, "roles": ["HANDLER", "MANAGER"], "remark": "挂起"},
        {"from": "ON_HOLD", "event": "RESUME", "to": null, "roles": ["HANDLER", "MANAGER"], "remark": "恢复"}
    ]}""")["rules"]
)

# 进程内规则缓存：整体不可变替换实现热重载（等价 Java volatile Map 语义）
_cache: dict[str, tuple[Rule, ...]] = {"DEFAULT": DEFAULT_RULES}


def parse_rules(raw: str) -> tuple[Rule, ...]:
    """解析并校验配置 JSON；非法即抛 ValueError（调用方映射为 1304）。"""
    data = json.loads(raw)
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("rules 必须为非空数组")
    result = []
    for index, item in enumerate(rules, start=1):
        prefix = f"第{index}条"
        from_status, event = item.get("from"), item.get("event")
        if from_status not in STATUS_LABELS:
            raise ValueError(f"{prefix}：源状态[{from_status}]非法")
        if not event or not isinstance(event, str):
            raise ValueError(f"{prefix}：事件必填")
        to = item.get("to")
        if to is not None and to not in STATUS_LABELS:
            raise ValueError(f"{prefix}：目标状态[{to}]非法")
        roles = item.get("roles") or []
        if not isinstance(roles, list) or any(r not in VALID_ROLES for r in roles):
            raise ValueError(f"{prefix}：角色仅允许 ADMIN/EXECUTIVE/MANAGER/HANDLER/REPORTER")
        result.append(Rule(from_status, event, to, frozenset(roles), item.get("remark") or ""))
    return tuple(result)


def validate_rules(raw: str) -> list[str]:
    """聚合校验配置 JSON（蓝本 parseRules 口径：所有错误收集后一次性返回，供保存时全量提示）。
    返回空列表 = 合法。event 追加枚举校验（比加载侧 parse_rules 严格，保存通过的配置加载必过）。"""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"JSON 解析失败: {exc.msg}"]
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list) or not rules:
        return ["rules 必须为非空数组"]
    errors: list[str] = []
    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            errors.append(f"第{index}条：须为对象")
            continue
        prefix = f"第{index}条"
        from_status, event = item.get("from"), item.get("event")
        if from_status not in STATUS_LABELS:
            errors.append(f"{prefix}：源状态[{from_status}]非法")
        if not event or not isinstance(event, str):
            errors.append(f"{prefix}：事件必填")
        elif event not in EVENT_LABELS:
            errors.append(f"{prefix}：事件[{event}]非法")
        to = item.get("to")
        if to is not None and to not in STATUS_LABELS:
            errors.append(f"{prefix}：目标状态[{to}]非法")
        roles = item.get("roles") or []
        if not isinstance(roles, list) or any(r not in VALID_ROLES for r in roles):
            errors.append(f"{prefix}：角色仅允许 ADMIN/EXECUTIVE/MANAGER/HANDLER/REPORTER")
    return errors


async def load_from_db(db: AsyncSession) -> list[dict[str, Any]]:
    """从配置表加载全部 ACTIVE 规则并原子替换缓存（热重载入口）。

    单条配置解析失败：跳过该 key、保留上一份可用配置（蓝本口径，不整体回滚）。
    """
    global _cache
    rows = (await db.execute(
        select(StateMachineConfig).where(StateMachineConfig.status == "ACTIVE")
    )).scalars().all()
    new_cache: dict[str, tuple[Rule, ...]] = {}
    loaded = []
    for row in rows:
        try:
            new_cache[row.config_key] = parse_rules(row.config_json)
        except (ValueError, json.JSONDecodeError):
            if row.config_key in _cache:  # 解析失败保留旧配置
                new_cache[row.config_key] = _cache[row.config_key]
        loaded.append({"key": row.config_key, "version": row.version,
                       "ruleCount": len(new_cache.get(row.config_key, ()))})
    if "DEFAULT" not in new_cache:
        new_cache["DEFAULT"] = DEFAULT_RULES
    _cache = new_cache
    return loaded


def rules_table(config_key: str = "DEFAULT") -> tuple[Rule, ...]:
    return _cache.get(config_key) or _cache["DEFAULT"]


def find_rule(from_status: str, event: str, config_key: str = "DEFAULT") -> Rule | None:
    return next((r for r in rules_table(config_key) if r.from_status == from_status and r.event == event), None)


def is_held(demand: Demand) -> bool:
    return demand.hold_snapshot_status is not None


def current_from(demand: Demand) -> str:
    """规则匹配视角的当前状态：挂起中一律视为 ON_HOLD。"""
    return ON_HOLD if is_held(demand) else demand.status


def check_role(
    rule: Rule, operator: User, operator_roles: frozenset[str] | set[str] | None = None,
) -> None:
    """角色校验：operator_roles 为有效角色（静态 ∪ 授权，由 role_service 解析）；缺省只看静态 role。"""
    if not rule.roles:
        return
    # ADMIN 直通（蓝本口径，含授权 ADMIN）；is_admin 兼容企微白名单过渡期
    from app.core.deps import is_admin

    roles = set(operator_roles) if operator_roles is not None else {operator.role}
    if "ADMIN" in roles or is_admin(operator):
        return
    if roles.isdisjoint(rule.roles):
        raise BizError(ErrorCode.FORBIDDEN, f"当前角色无权执行[{EVENT_LABELS.get(rule.event, rule.event)}]")


def available_events(
    demand: Demand, operator: User, config_key: str = "DEFAULT",
    operator_roles: frozenset[str] | set[str] | None = None,
) -> list[str]:
    """当前状态下、当前角色可触发的事件列表（不含业务归属校验，由 flow_service 叠加）。"""
    from_status = current_from(demand)
    events = []
    for rule in rules_table(config_key):
        if rule.from_status != from_status:
            continue
        try:
            check_role(rule, operator, operator_roles)
        except BizError:
            continue
        events.append(rule.event)
    return events


FieldUpdate = Callable[[Demand], None] | dict[str, Any] | None


async def transition(
    db: AsyncSession,
    demand_id: int,
    event: str,
    operator: User,
    *,
    comment: str | None = None,
    extra: dict[str, Any] | None = None,
    field_update: FieldUpdate = None,
    config_key: str = "DEFAULT",
) -> DemandTransitionLog:
    """执行一次状态流转：行锁 → 规则匹配 → 角色校验 → 应用状态 → 写 transition_log（同事务）。

    - 行锁（SELECT ... FOR UPDATE）串行化并发流转；并发领取在规则匹配处自然失败
    - field_update：业务层钩子（如分派人/关闭时间/评分），dict 或 callable
    - 返回写入的流转日志
    """
    if operator is None:
        raise BizError(ErrorCode.UNAUTHORIZED)
    demand = (await db.execute(
        select(Demand).where(Demand.id == demand_id).with_for_update()
    )).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)

    from_status = current_from(demand)
    rule = find_rule(from_status, event, config_key)
    if rule is None:
        raise BizError(
            ErrorCode.ILLEGAL_STATE_TRANSITION,
            f"当前状态[{STATUS_LABELS.get(from_status, from_status)}]不允许执行[{EVENT_LABELS.get(event, event)}]",
        )
    if rule.roles:
        # 有效角色 = 静态 role ∪ 生效授权（role_service，延迟导入避免 core→services 循环依赖）
        from app.services import role_service

        check_role(rule, operator, await role_service.effective_roles(db, operator))
    else:
        check_role(rule, operator)

    hold_flag = False
    if event == "HOLD":
        # 叠加态：主状态列不动，快照当前主态 + 记录原因
        demand.hold_snapshot_status = demand.status
        demand.hold_reason = (comment or "").strip() or None
        to_status = ON_HOLD
        hold_flag = True
    elif event == "RESUME":
        to_status = demand.hold_snapshot_status
        demand.hold_snapshot_status = None
        demand.hold_reason = None
        hold_flag = True
    elif rule.to is None:
        # CHANGE_TYPE 等主状态不变的事件
        to_status = demand.status
    else:
        demand.status = rule.to
        to_status = rule.to

    if callable(field_update):
        field_update(demand)
    elif field_update:
        for key, value in field_update.items():
            setattr(demand, key, value)

    demand.revision += 1
    demand.updated_at = now()
    log = DemandTransitionLog(
        demand_id=demand.id,
        from_status=from_status,
        to_status=to_status,
        event=event,
        operator_id=operator.id,
        operator_snapshot=operator.name,
        hold_flag=hold_flag,
        comment=comment,
        extra=extra or None,
    )
    db.add(log)
    await db.flush()

    # 通知钩子：同事务写信箱（一期 IN_APP 写入即送达；SLA_ALERT 由扫描任务触发不经此）。
    # 与 role_service 同套路延迟导入避免 core→services 循环依赖；RETURN_POOL/SPLIT 等无映射事件内部直接跳过
    from app.services import notification_service

    await notification_service.notify_transition(
        db, demand=demand, event=event, from_status=from_status, to_status=to_status,
        operator=operator, comment=comment, extra=extra)
    return log


async def write_transition_log(
    db: AsyncSession,
    demand: Demand,
    event: str,
    operator: User,
    *,
    from_status: str | None = None,
    to_status: str,
    comment: str | None = None,
    extra: dict[str, Any] | None = None,
) -> DemandTransitionLog:
    """非状态机事件（SPLIT 建单）的流转日志直写：仅用于不改变父状态的旁路建单。"""
    log = DemandTransitionLog(
        demand_id=demand.id, from_status=from_status, to_status=to_status, event=event,
        operator_id=operator.id, operator_snapshot=operator.name, comment=comment, extra=extra or None,
    )
    db.add(log)
    await db.flush()
    return log


def serialize_log(log: DemandTransitionLog) -> dict[str, Any]:
    from app.core.result import encode

    return {
        "id": log.id,
        "demandId": log.demand_id,
        "fromStatus": log.from_status,
        "fromStatusLabel": STATUS_LABELS.get(log.from_status or "", log.from_status),
        "toStatus": log.to_status,
        "toStatusLabel": STATUS_LABELS.get(log.to_status, log.to_status),
        "event": log.event,
        "eventLabel": EVENT_LABELS.get(log.event, log.event),
        "operatorId": log.operator_id,
        "operatorName": log.operator_snapshot,
        "holdFlag": log.hold_flag,
        "comment": log.comment,
        "extra": log.extra,
        "createdAt": encode(log.created_at),
    }


async def list_logs(db: AsyncSession, demand_id: int) -> list[DemandTransitionLog]:
    return list((await db.execute(
        select(DemandTransitionLog)
        .where(DemandTransitionLog.demand_id == demand_id)
        .order_by(DemandTransitionLog.id)
    )).scalars())


def events_label_map(events: Iterable[str]) -> list[dict[str, str]]:
    return [{"event": e, "label": EVENT_LABELS.get(e, e)} for e in events]
