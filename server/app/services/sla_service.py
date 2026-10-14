"""SLA 超时扫描：黄/红两档预警 + notify_dedupe 七天去重（蓝本 SlaScanJob 口径）。

白话：需求在一个状态里"泡"太久，系统就发站内信催办——快到期限发黄牌，已超期限发红牌。
- 扫描口径：sla_config enabled=1 的「类型 × 状态」组合；挂起中（ON_HOLD 叠加态）豁免告警
- 停留时长：最后一条 to_status=当前状态的流转日志时间；无日志兜底 submitted_at→created_at；
  RESUME 恢复会写新流转日志，时钟自然重置（蓝本同口径）
- 档位：elapsed>=max→红色告警（已超时）；>=warn→黄色预警（即将超时）；每轮只取最高档
- 去重：notify_dedupe 表 key=sla:alert:{LEVEL}:{demandId}:{status}（蓝本 Redis SETNX 口径），
  7 天内同 demand 同状态同档位仅一次；每轮先清理 7 天前 key（=TTL 语义）；
  通知与去重 key 同事务写入——异常整体回滚，下轮重试；通知未落地（模板缺失等）不写 key
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db_session
from app.db.models import Demand, DemandTransitionLog, NotifyDedupe, SlaConfig, now
from app.services import notification_service

logger = logging.getLogger(__name__)

LEVEL_YELLOW = "YELLOW"
LEVEL_RED = "RED"
LEVEL_TEXT = {LEVEL_YELLOW: "黄色预警（即将超时）", LEVEL_RED: "红色告警（已超时）"}
DEDUPE_TTL_DAYS = 7


def dedupe_key(level: str, demand_id: int, status: str) -> str:
    return f"sla:alert:{level}:{demand_id}:{status}"


async def _entered_at_map(
    db: AsyncSession, demand_ids: list[int], status: str,
) -> dict[int, object]:
    """各需求进入当前状态的时刻：最后一条 to_status=当前状态的流转日志时间。"""
    if not demand_ids:
        return {}
    rows = (await db.execute(
        select(DemandTransitionLog.demand_id, func.max(DemandTransitionLog.created_at))
        .where(DemandTransitionLog.demand_id.in_(demand_ids),
               DemandTransitionLog.to_status == status)
        .group_by(DemandTransitionLog.demand_id)
    )).all()
    return dict(rows)


async def scan_once(db: AsyncSession) -> dict[str, int]:
    """扫一轮：返回统计（scanned/yellow/red/deduped）。调用方持有事务。"""
    # 7 天前去重 key 过期清理（=蓝本 Redis TTL 语义）
    await db.execute(delete(NotifyDedupe).where(
        NotifyDedupe.created_at < now() - timedelta(days=DEDUPE_TTL_DAYS)))

    configs = (await db.execute(
        select(SlaConfig).where(SlaConfig.enabled.is_(True))
    )).scalars().all()
    stats = {"scanned": 0, "yellow": 0, "red": 0, "deduped": 0}
    current = now()
    for config in configs:
        demands = (await db.execute(
            select(Demand).where(Demand.demand_type_code == config.demand_type_code,
                                 Demand.status == config.status,
                                 Demand.hold_snapshot_status.is_(None))
        )).scalars().all()
        if not demands:
            continue
        entered = await _entered_at_map(db, [d.id for d in demands], config.status)
        stats["scanned"] += len(demands)
        for demand in demands:
            entered_at = entered.get(demand.id) or demand.submitted_at or demand.created_at
            elapsed_minutes = int((current - entered_at).total_seconds() // 60)
            if elapsed_minutes >= config.max_minutes:
                level = LEVEL_RED
            elif elapsed_minutes >= config.warn_minutes:
                level = LEVEL_YELLOW
            else:
                continue
            key = dedupe_key(level, demand.id, config.status)
            exists = (await db.execute(
                select(func.count(NotifyDedupe.id)).where(NotifyDedupe.dedupe_key == key)
            )).scalar_one()
            if exists:
                stats["deduped"] += 1
                continue
            written = await notification_service.notify_transition(
                db, demand=demand, event="SLA_ALERT", from_status=None, to_status=config.status,
                operator=None, comment=None,
                extra={"level": level, "levelText": LEVEL_TEXT[level],
                       "elapsedMinutes": elapsed_minutes,
                       "warnMinutes": config.warn_minutes, "maxMinutes": config.max_minutes,
                       "operatorName": "系统"})
            if written:
                db.add(NotifyDedupe(dedupe_key=key))
                await db.flush()
                stats["yellow" if level == LEVEL_YELLOW else "red"] += 1
    return stats


async def scan_loop(stop: asyncio.Event, interval_seconds: int) -> None:
    """定时扫描循环（asyncio 先例，无外部调度器）：每轮独立事务，异常记日志下轮继续。"""
    while not stop.is_set():
        try:
            factory = db_session.get_session_factory()  # 模块属性访问：测试 monkeypatch 受控 factory 生效
            async with factory() as db:
                async with db.begin():
                    stats = await scan_once(db)
            if stats["yellow"] or stats["red"]:
                logger.info("SLA 扫描告警: %s", stats)
        except Exception:
            logger.warning("SLA 扫描轮次异常", exc_info=True)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass


def start_scanner(interval_seconds: int) -> tuple[asyncio.Task, asyncio.Event]:
    """启动后台扫描任务；返回 (task, stop)，关停时 set stop 并 await task。"""
    stop = asyncio.Event()
    return asyncio.create_task(scan_loop(stop, interval_seconds)), stop
