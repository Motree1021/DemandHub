"""统计看板与 demand_stat_daily 当日快照（蓝本 DashboardService + StatDailyJob 口径）。

白话：看板是"现算现看"——经理/管理者打开页面时按实时 SQL 汇总；demand_stat_daily
只是把"今天的快照"定时存一份，供后续离线分析，一期看板不读它。
- 看板实时 SQL（蓝本同口径，不读预聚合表）；DataScope 一期=全量（所有角色看全部数据）
- 经理看板 kpi：monthNew=本月 1 号至今提交数；inflight=已提交未关闭（不含草稿/完成/关闭）；
  done=范围内关闭且 status=DONE；avgCycleHours=submitted→closed 均值保留 1 位
- slaHealth：在途未挂起单按 (类型,状态) 命中 sla_config，"进入当前状态时刻"=末条
  to_status=当前状态的流转日志（兜底 submitted_at→created_at，与 sla_service 同源）；
  elapsed>=max→over、>=warn→warn、无配置→normal
- 组织维度一期无组织服务：orgBacklog 按 models.py 注释改走 submitter_dept 快照（deptBacklog）；
  快照表 org 列 IFNULL→0
- 快照刷新：delete 当日 + 重算插入（同事务幂等，等价蓝本 INSERT ON DUPLICATE KEY UPDATE）；
  只刷当日，历史日期不回刷
"""

import asyncio
import logging
from datetime import date, timedelta

from sqlalchemy import case, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db import session as db_session
from app.db.models import (
    Demand,
    DemandStatDaily,
    DemandTransitionLog,
    EffortLog,
    SlaConfig,
    User,
    now,
)

logger = logging.getLogger(__name__)

INFLIGHT_EXCLUDE = ("DRAFT", "DONE", "CLOSED")  # 在途 = 已提交未闭环
PROCESSING_STATUSES = ("ANALYZING", "SOLUTION_REVIEW", "CONFIRMED", "IN_PROGRESS", "ACCEPTANCE")
RANGE_KINDS = ("week", "month", "quarter", "custom")


def resolve_range(range_kind: str, from_date: date | None, to_date: date | None) -> tuple[object, object]:
    """时间范围 [from, to)。week=本周一；month=本月 1 号；quarter=本季度首月 1 号；custom 需传 from/to。"""
    if range_kind not in RANGE_KINDS:
        raise BizError(ErrorCode.PARAM_INVALID, "时间范围仅支持 week/month/quarter/custom")
    today = now().date()
    if range_kind == "custom":
        if from_date is None or to_date is None:
            raise BizError(ErrorCode.PARAM_INVALID, "自定义范围需同时传 from 与 to")
        start, end = from_date, to_date + timedelta(days=1)
    elif range_kind == "week":
        start, end = today - timedelta(days=today.weekday()), today + timedelta(days=1)
    elif range_kind == "month":
        start, end = today.replace(day=1), today + timedelta(days=1)
    else:
        quarter_first_month = (today.month - 1) // 3 * 3 + 1
        start, end = today.replace(month=quarter_first_month, day=1), today + timedelta(days=1)
    if start > end:
        raise BizError(ErrorCode.PARAM_INVALID, "开始日期不能晚于结束日期")
    return start, end


def _inflight_cond():
    return Demand.status.notin_(INFLIGHT_EXCLUDE)


async def _cycle_hours(db: AsyncSession, start, end) -> float | None:
    """范围内 DONE 单的 submitted→closed 平均小时（蓝本 avgCycleHours，保留 1 位）。"""
    minutes = func.avg(func.timestampdiff(text("MINUTE"), Demand.submitted_at, Demand.closed_at))
    value = (await db.execute(
        select(minutes).where(Demand.status == "DONE",
                              Demand.closed_at.is_not(None), Demand.submitted_at.is_not(None),
                              Demand.closed_at >= start, Demand.closed_at < end)
    )).scalar_one()
    return None if value is None else round(float(value) / 60, 1)


async def _sla_health(db: AsyncSession) -> dict[str, int]:
    """在途未挂起单的 SLA 健康度 {normal, warn, over}（与 sla_service 计时口径同源）。"""
    configs = (await db.execute(
        select(SlaConfig).where(SlaConfig.enabled.is_(True))
    )).scalars().all()
    config_map = {(c.demand_type_code, c.status): c for c in configs}
    demands = (await db.execute(
        select(Demand).where(_inflight_cond(), Demand.hold_snapshot_status.is_(None))
    )).scalars().all()
    health = {"normal": 0, "warn": 0, "over": 0}
    if not demands:
        return health
    # 按状态分批取「进入当前状态时刻」（末条 to_status=当前状态的流转日志）
    entered: dict[int, object] = {}
    for status in {d.status for d in demands}:
        ids = [d.id for d in demands if d.status == status]
        rows = (await db.execute(
            select(DemandTransitionLog.demand_id, func.max(DemandTransitionLog.created_at))
            .where(DemandTransitionLog.demand_id.in_(ids), DemandTransitionLog.to_status == status)
            .group_by(DemandTransitionLog.demand_id)
        )).all()
        entered.update(dict(rows))
    current = now()
    for demand in demands:
        config = config_map.get((demand.demand_type_code, demand.status))
        if config is None:
            health["normal"] += 1
            continue
        entered_at = entered.get(demand.id) or demand.submitted_at or demand.created_at
        elapsed_minutes = int((current - entered_at).total_seconds() // 60)
        if elapsed_minutes >= config.max_minutes:
            health["over"] += 1
        elif elapsed_minutes >= config.warn_minutes:
            health["warn"] += 1
        else:
            health["normal"] += 1
    return health


async def manager_board(db: AsyncSession, range_kind: str = "month",
                        from_date: date | None = None, to_date: date | None = None) -> dict:
    """经理/管理者看板（蓝本 ManagerBoardVO）：kpi + 12 周趋势 + 类型/渠道分布 + 部门在途 + SLA。"""
    start, end = resolve_range(range_kind, from_date, to_date)
    month_start = now().date().replace(day=1)

    month_new = (await db.execute(select(func.count(Demand.id)).where(
        Demand.submitted_at.is_not(None), Demand.submitted_at >= month_start))).scalar_one()
    inflight = (await db.execute(select(func.count(Demand.id)).where(_inflight_cond()))).scalar_one()
    done = (await db.execute(select(func.count(Demand.id)).where(
        Demand.status == "DONE", Demand.closed_at >= start, Demand.closed_at < end))).scalar_one()
    sla_health = await _sla_health(db)
    kpi = {"monthNew": month_new, "inflight": inflight, "done": done,
           "slaOver": sla_health["over"], "avgCycleHours": await _cycle_hours(db, start, end)}

    # 近 12 周趋势（周一起算）：newCnt=submitted_at 落桶、doneCnt=DONE 且 closed_at 落桶
    monday = now().date() - timedelta(days=now().date().weekday())
    trend = []
    for offset in range(11, -1, -1):
        week_start = monday - timedelta(weeks=offset)
        week_end = week_start + timedelta(days=7)
        new_cnt = (await db.execute(select(func.count(Demand.id)).where(
            Demand.submitted_at >= week_start, Demand.submitted_at < week_end))).scalar_one()
        done_cnt = (await db.execute(select(func.count(Demand.id)).where(
            Demand.status == "DONE",
            Demand.closed_at >= week_start, Demand.closed_at < week_end))).scalar_one()
        trend.append({"weekStart": week_start, "newCnt": new_cnt, "doneCnt": done_cnt})

    type_rows = (await db.execute(
        select(Demand.demand_type_code, func.count(Demand.id))
        .where(Demand.submitted_at >= start, Demand.submitted_at < end)
        .group_by(Demand.demand_type_code).order_by(func.count(Demand.id).desc())
    )).all()
    type_distribution = [{"typeCode": code or "未知", "cnt": cnt} for code, cnt in type_rows]

    channel_col = func.coalesce(Demand.channel, "未知")
    channel_rows = (await db.execute(
        select(channel_col, func.count(Demand.id))
        .where(Demand.submitted_at >= start, Demand.submitted_at < end)
        .group_by(channel_col).order_by(func.count(Demand.id).desc())
    )).all()
    channel_distribution = [{"channel": channel, "cnt": cnt} for channel, cnt in channel_rows]

    # 蓝本 orgBacklog Top10：一期无组织服务，按 models.py 注释走 submitter_dept 快照
    dept_col = func.coalesce(Demand.submitter_dept, "未填写")
    dept_rows = (await db.execute(
        select(dept_col, func.count(Demand.id))
        .where(_inflight_cond())
        .group_by(dept_col).order_by(func.count(Demand.id).desc()).limit(10)
    )).all()
    dept_backlog = [{"dept": dept, "cnt": cnt} for dept, cnt in dept_rows]

    return {"kpi": kpi, "trend": trend, "typeDistribution": type_distribution,
            "channelDistribution": channel_distribution, "deptBacklog": dept_backlog,
            "slaHealth": sla_health}


async def org_board(db: AsyncSession, range_kind: str = "month",
                    from_date: date | None = None, to_date: date | None = None) -> dict:
    """组织看板（蓝本 OrgBoardVO）：受理/处理池/处理中/本周完成/人均在途/成员工作量。"""
    start, end = resolve_range(range_kind, from_date, to_date)
    monday = now().date() - timedelta(days=now().date().weekday())

    pending_accept = (await db.execute(select(func.count(Demand.id)).where(
        Demand.status == "SUBMITTED"))).scalar_one()
    pool = (await db.execute(select(func.count(Demand.id)).where(
        Demand.status == "TRIAGE"))).scalar_one()
    processing = (await db.execute(select(func.count(Demand.id)).where(
        Demand.status.in_(PROCESSING_STATUSES)))).scalar_one()
    week_done = (await db.execute(select(func.count(Demand.id)).where(
        Demand.status == "DONE", Demand.closed_at >= monday))).scalar_one()

    inflight_rows = (await db.execute(
        select(Demand.assignee_id, func.count(Demand.id))
        .where(_inflight_cond(), Demand.assignee_id.is_not(None))
        .group_by(Demand.assignee_id)
    )).all()
    inflight_map = dict(inflight_rows)
    avg_inflight = (round(sum(inflight_map.values()) / len(inflight_map), 1)
                    if inflight_map else 0.0)

    effort_rows = (await db.execute(
        select(EffortLog.user_id, func.coalesce(func.sum(EffortLog.hours), 0))
        .where(EffortLog.work_date >= start, EffortLog.work_date < end)
        .group_by(EffortLog.user_id)
    )).all()
    effort_map = {user_id: float(hours) for user_id, hours in effort_rows}

    member_ids = set(inflight_map) | set(effort_map)
    member_workload = []
    if member_ids:
        users = (await db.execute(
            select(User).where(User.id.in_(member_ids))
        )).scalars().all()
        member_workload = sorted(
            ({"userId": u.id, "userName": u.name,
              "inflightCnt": inflight_map.get(u.id, 0),
              "effortHours": effort_map.get(u.id, 0.0)} for u in users),
            key=lambda row: (-row["inflightCnt"], -row["effortHours"], row["userId"]))

    return {"pendingAccept": pending_accept, "pool": pool, "processing": processing,
            "weekDone": week_done, "avgInflightPerHandler": avg_inflight,
            "memberWorkload": member_workload}


async def refresh_today(db: AsyncSession) -> int:
    """重算当日快照：delete 当日 + 按当前 demand 表重聚合插入（同事务幂等）。返回写入行数。"""
    today = now().date()
    await db.execute(delete(DemandStatDaily).where(DemandStatDaily.stat_date == today))
    cycle_hours = func.avg(case(
        (Demand.closed_at.is_not(None) & Demand.submitted_at.is_not(None),
         func.timestampdiff(text("MINUTE"), Demand.submitted_at, Demand.closed_at) / 60.0),
        else_=None))
    rows = (await db.execute(
        select(Demand.demand_type_code,
               func.coalesce(Demand.assignee_org_id, 0),
               func.coalesce(Demand.submitter_org_id, 0),
               Demand.status,
               func.count(Demand.id),
               cycle_hours)
        .group_by(Demand.demand_type_code,
                  func.coalesce(Demand.assignee_org_id, 0),
                  func.coalesce(Demand.submitter_org_id, 0),
                  Demand.status)
    )).all()
    for type_code, assignee_org, submitter_org, status, cnt, avg_hours in rows:
        db.add(DemandStatDaily(
            stat_date=today, demand_type_code=type_code or "未知",
            assignee_org_id=assignee_org, reporter_org_id=submitter_org,
            status=status, cnt=cnt,
            avg_cycle_hours=None if avg_hours is None else round(float(avg_hours), 2)))
    await db.flush()
    return len(rows)


async def refresh_loop(stop: asyncio.Event, interval_seconds: int) -> None:
    """定时刷新当日快照（asyncio 先例，同 sla_service.scan_loop）：每轮独立事务，异常下轮继续。"""
    while not stop.is_set():
        try:
            factory = db_session.get_session_factory()  # 模块属性访问：测试 monkeypatch 受控 factory 生效
            async with factory() as db:
                async with db.begin():
                    rows = await refresh_today(db)
            logger.info("统计快照刷新: 写入 %s 行", rows)
        except Exception:
            logger.warning("统计快照刷新轮次异常", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


def start_refresher(interval_seconds: int) -> tuple[asyncio.Task, asyncio.Event]:
    """启动后台快照刷新任务；返回 (task, stop)，关停时 set stop 并 await task。"""
    stop = asyncio.Event()
    return asyncio.create_task(refresh_loop(stop, interval_seconds)), stop
