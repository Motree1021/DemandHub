"""P4 SLA 超时扫描单测（2026-10-14）。

覆盖口径（对应验收门禁「SLA 扫描去重」）：
- 黄/红两档：elapsed>=warn 黄色预警、>=max 红色告警、未到线不告警；每轮只取最高档
- 停留时长：最后一条 to_status=当前状态的流转日志；无日志兜底 submitted_at；RESUME 新日志重置时钟
- 挂起豁免（ON_HOLD 叠加态不告警）
- 去重：同 demand 同状态同档位 7 天内仅一次；7 天前 key 扫描时清理（TTL 语义）可再次告警
- 通知未落地（模板缺失）不写去重 key，下轮可重试；配置 enabled=0 静默跳过
- 接收人：处理人 + 经理（授权范围过滤）+ EXECUTIVE 直通（蓝本 RecipientResolver.SLA_ALERT）
"""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import (
    Demand,
    DemandTransitionLog,
    Notification,
    NotificationTemplate,
    NotifyDedupe,
    SlaConfig,
    User,
    now,
)
from app.services import role_service, sla_service

SLA_TITLE = "SLA${level_text}：${demand_no}"
SLA_CONTENT = "需求${demand_no}「${title}」在状态「${to_status}」已停留${elapsed_minutes}分钟，${level_text}"


# ---- 基座工具 ----

async def make_user(factory, name, wecom_userid, role="HANDLER"):
    async with factory() as db:
        async with db.begin():
            user = User(name=name, wecom_userid=wecom_userid, channel="CHUANGJIN_LS", role=role)
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


@pytest.fixture
async def submitter(session_factory):
    return await make_user(session_factory, "提报人", "p4s-submitter")


@pytest.fixture(autouse=True)
async def sla_seed(session_factory):
    """铺 SLA 模板与配置（conftest 清库会抹掉迁移种子）：TECH×SUBMITTED 60/120 分钟。"""
    async with session_factory() as db:
        async with db.begin():
            db.add(NotificationTemplate(
                template_code="SLA_ALERT", template_name="SLA 告警",
                title_template=SLA_TITLE, content_template=SLA_CONTENT))
            db.add(SlaConfig(demand_type_code="TECH", status="SUBMITTED",
                             warn_minutes=60, max_minutes=120))
    return True


async def insert_demand(factory, submitter, minutes_ago=0, **overrides):
    async with factory() as db:
        async with db.begin():
            moment = now() - timedelta(minutes=minutes_ago)
            demand = Demand(
                title="夹具需求", demand_type_code="TECH", content="内容", urgency="NORMAL",
                status="SUBMITTED", submitter_id=submitter.id, submitter_name=submitter.name,
                channel="CHUANGJIN_LS", client_request_id=f"raw-{uuid4().hex}",
                create_request_hash="raw", submitted_at=moment, revision=0,
                created_at=moment, updated_at=moment)
            for key, value in overrides.items():
                setattr(demand, key, value)
            db.add(demand)
            await db.flush()
            return demand.id


async def add_log(factory, demand_id, operator_id, to_status, minutes_ago, event="SUBMIT"):
    async with factory() as db:
        async with db.begin():
            db.add(DemandTransitionLog(
                demand_id=demand_id, from_status="DRAFT", to_status=to_status, event=event,
                operator_id=operator_id, created_at=now() - timedelta(minutes=minutes_ago)))


async def scan(factory):
    async with factory() as db:
        async with db.begin():
            return await sla_service.scan_once(db)


async def mails(factory, receiver_id):
    async with factory() as db:
        return list((await db.execute(
            select(Notification).where(Notification.receiver_id == receiver_id)
            .order_by(Notification.id))).scalars().all())


async def dedupe_rows(factory):
    async with factory() as db:
        return list((await db.execute(select(NotifyDedupe))).scalars().all())


# ---- 1. 档位与变量 ----

@pytest.mark.asyncio
async def test_yellow_alert_vars_and_recipients(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4s-mgr", role="MANAGER")
    executive = await make_user(session_factory, "管理者", "p4s-exec", role="EXECUTIVE")
    did = await insert_demand(session_factory, submitter, minutes_ago=200)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=70)
    stats = await scan(session_factory)
    assert stats["yellow"] == 1 and stats["red"] == 0
    for user in (manager, executive):
        found = await mails(session_factory, user.id)
        assert len(found) == 1
        assert "黄色预警（即将超时）" in found[0].title
        assert "已停留70分钟" in found[0].content
        assert "「SUBMITTED」" in found[0].content  # 状态码原样（决策④）


@pytest.mark.asyncio
async def test_red_alert_over_max(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4s-mgr2", role="MANAGER")
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=130)
    stats = await scan(session_factory)
    assert stats["red"] == 1 and stats["yellow"] == 0
    found = await mails(session_factory, manager.id)
    assert "红色告警（已超时）" in found[0].title


@pytest.mark.asyncio
async def test_below_warn_no_alert(session_factory, submitter):
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=30)
    stats = await scan(session_factory)
    assert stats["scanned"] == 1 and stats["yellow"] == 0 and stats["red"] == 0
    assert await dedupe_rows(session_factory) == []


@pytest.mark.asyncio
async def test_assignee_receives_alert(session_factory, submitter):
    handler = await make_user(session_factory, "处理人", "p4s-hdl")
    did = await insert_demand(session_factory, submitter, assignee_id=handler.id)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=70)
    await scan(session_factory)
    assert len(await mails(session_factory, handler.id)) == 1


# ---- 2. 计时口径 ----

@pytest.mark.asyncio
async def test_resume_log_resets_clock(session_factory, submitter):
    """老日志 200 分钟 + 恢复新日志 5 分钟：按最新日志计时 → 不告警。"""
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=200)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=5, event="RESUME")
    stats = await scan(session_factory)
    assert stats["yellow"] == 0 and stats["red"] == 0


@pytest.mark.asyncio
async def test_fallback_to_submitted_at(session_factory, submitter):
    """无流转日志：兜底 submitted_at 计时。"""
    await make_user(session_factory, "经理", "p4s-mgr5", role="MANAGER")
    await insert_demand(session_factory, submitter, minutes_ago=70)
    stats = await scan(session_factory)
    assert stats["yellow"] == 1


@pytest.mark.asyncio
async def test_held_demand_exempt(session_factory, submitter):
    did = await insert_demand(session_factory, submitter, hold_snapshot_status="SUBMITTED",
                              hold_reason="等数据")
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=200)
    stats = await scan(session_factory)
    assert stats["scanned"] == 0 and stats["red"] == 0


# ---- 3. 去重 ----

@pytest.mark.asyncio
async def test_dedupe_same_level_once(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4s-mgr3", role="MANAGER")
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=70)
    first = await scan(session_factory)
    assert first["yellow"] == 1
    rows = await dedupe_rows(session_factory)
    assert [row.dedupe_key for row in rows] == [f"sla:alert:YELLOW:{did}:SUBMITTED"]
    second = await scan(session_factory)
    assert second["yellow"] == 0 and second["deduped"] == 1
    assert len(await mails(session_factory, manager.id)) == 1


@pytest.mark.asyncio
async def test_dedupe_expires_after_7_days(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4s-mgr4", role="MANAGER")
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=70)
    async with session_factory() as db:
        async with db.begin():
            db.add(NotifyDedupe(
                dedupe_key=f"sla:alert:YELLOW:{did}:SUBMITTED",
                created_at=now() - timedelta(days=8)))
    stats = await scan(session_factory)
    assert stats["yellow"] == 1  # 旧 key 过期清理，重新告警
    rows = await dedupe_rows(session_factory)
    assert len(rows) == 1 and rows[0].created_at > now() - timedelta(days=1)
    assert len(await mails(session_factory, manager.id)) == 1


@pytest.mark.asyncio
async def test_no_dedupe_key_when_template_missing(session_factory, submitter):
    """通知未落地不写去重 key：模板停用时不告警、不留 key，恢复模板后下轮可重试。"""
    async with session_factory() as db:
        async with db.begin():
            row = (await db.execute(
                select(NotificationTemplate).where(NotificationTemplate.template_code == "SLA_ALERT")
            )).scalar_one()
            row.status = "INACTIVE"
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=70)
    stats = await scan(session_factory)
    assert stats["yellow"] == 0
    assert await dedupe_rows(session_factory) == []


# ---- 4. 配置与接收人范围 ----

@pytest.mark.asyncio
async def test_disabled_config_skipped(session_factory, submitter):
    async with session_factory() as db:
        async with db.begin():
            config = (await db.execute(select(SlaConfig))).scalar_one()
            config.enabled = False
    did = await insert_demand(session_factory, submitter)
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=200)
    stats = await scan(session_factory)
    assert stats["scanned"] == 0 and stats["red"] == 0


@pytest.mark.asyncio
async def test_grant_scope_filters_manager_executive_bypass(session_factory, submitter):
    """授权经理范围外不收（决策③）；EXECUTIVE 直通全类型。"""
    scoped = await make_user(session_factory, "授权经理", "p4s-gmgr")
    executive = await make_user(session_factory, "管理者", "p4s-exec2", role="EXECUTIVE")
    async with session_factory() as db:
        async with db.begin():
            await role_service.create_grant(
                db, user_id=scoped.id, role_code="MANAGER", org_id=None,
                demand_type_scope="MATL", effective_from=None, effective_to=None, granted_by=None)
    did = await insert_demand(session_factory, submitter)  # TECH，不在授权范围
    await add_log(session_factory, did, submitter.id, "SUBMITTED", minutes_ago=70)
    await scan(session_factory)
    assert await mails(session_factory, scoped.id) == []
    assert len(await mails(session_factory, executive.id)) == 1


@pytest.mark.asyncio
async def test_scan_loop_start_stop(session_factory, monkeypatch):
    """后台循环：受控 factory 注入跑一轮后干净关停（asyncio 先例）。"""
    import asyncio

    from app.db import session as db_session

    monkeypatch.setattr(db_session, "get_session_factory", lambda: session_factory)
    task, stop = sla_service.start_scanner(interval_seconds=3600)
    for _ in range(50):  # 等首轮扫描落库
        rows = await dedupe_rows(session_factory)
        if rows:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    did_rows = await dedupe_rows(session_factory)
    assert task.done() and did_rows == []  # 本轮无超时需求，仅验证循环可跑可停
