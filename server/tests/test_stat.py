"""P4 统计看板单测（2026-10-14）。

覆盖口径（对应验收门禁「看板数据与快照一致」）：
- 经理看板 kpi：monthNew=本月提交、inflight=已提交未闭环（不含草稿）、done=范围内 DONE、
  avgCycleHours=submitted→closed 均值保留 1 位
- 12 周趋势周一起算；类型/渠道分布走范围 submitted_at（channel NULL→未知）
- deptBacklog：一期无组织服务，orgBacklog 改走 submitter_dept 快照（models.py 注释口径）
- slaHealth：末条流转日志计时（兜底 submitted_at），挂起豁免，无配置→normal
- 组织看板：受理/处理池/处理中/本周完成/人均在途/成员工作量（工时在范围内才计）
- refresh_today：只刷当日快照，delete+重插幂等，历史日期不动；org 列 IFNULL→0
- API：require_role 守卫（HANDLER 403、MANAGER/EXECUTIVE 放行、stat-refresh 仅 ADMIN/EXECUTIVE）
"""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import BizError
from app.db.models import (
    Demand,
    DemandStatDaily,
    DemandTransitionLog,
    EffortLog,
    SlaConfig,
    User,
    now,
)
from app.services import stat_service

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
    return await make_user(session_factory, "提报人", "p4t-submitter")


async def insert_demand(factory, submitter, minutes_ago=0, **overrides):
    async with factory() as db:
        async with db.begin():
            moment = now() - timedelta(minutes=minutes_ago)
            demand = Demand(
                title="看板需求", demand_type_code="TECH", content="内容", urgency="NORMAL",
                status="SUBMITTED", submitter_id=submitter.id, submitter_name=submitter.name,
                channel="CHUANGJIN_LS", client_request_id=f"raw-{uuid4().hex}",
                create_request_hash="raw", submitted_at=moment, revision=0,
                created_at=moment, updated_at=moment)
            for key, value in overrides.items():
                setattr(demand, key, value)
            db.add(demand)
            await db.flush()
            return demand.id


async def board(factory, *args, **kwargs):
    async with factory() as db:
        return await stat_service.manager_board(db, *args, **kwargs)


# ---- 1. 时间范围 ----

def test_resolve_range_kinds():
    week_start, _ = stat_service.resolve_range("week", None, None)
    assert week_start.weekday() == 0 and week_start <= now().date()
    month_start, _ = stat_service.resolve_range("month", None, None)
    assert month_start.day == 1
    quarter_start, _ = stat_service.resolve_range("quarter", None, None)
    assert quarter_start.day == 1 and quarter_start.month in (1, 4, 7, 10)
    with pytest.raises(BizError):
        stat_service.resolve_range("year", None, None)
    with pytest.raises(BizError):
        stat_service.resolve_range("custom", None, None)


# ---- 2. 经理看板 kpi ----

@pytest.mark.asyncio
async def test_kpi_counts(session_factory, submitter):
    await insert_demand(session_factory, submitter, status="SUBMITTED")
    await insert_demand(session_factory, submitter, status="TRIAGE")
    await insert_demand(session_factory, submitter, status="IN_PROGRESS")
    await insert_demand(session_factory, submitter, status="DRAFT", submitted_at=None)
    await insert_demand(session_factory, submitter, minutes_ago=60 * 24 * 2,
                        status="DONE", closed_at=now())
    await insert_demand(session_factory, submitter, status="CLOSED", closed_at=now())
    await insert_demand(session_factory, submitter, minutes_ago=60 * 24 * 40)  # 上月提交
    data = await board(session_factory)
    kpi = data["kpi"]
    assert kpi["monthNew"] == 5  # 本月提交（今天 3 单 + DONE 2 天前 + CLOSED 今天；不含草稿与上月单）
    assert kpi["inflight"] == 4  # SUBMITTED/TRIAGE/IN_PROGRESS + 上月仍在途
    assert kpi["done"] == 1
    assert kpi["slaOver"] == 0  # 无 sla_config → 全部 normal


@pytest.mark.asyncio
async def test_avg_cycle_hours_rounding(session_factory, submitter):
    await insert_demand(session_factory, submitter, minutes_ago=120,
                        status="DONE", closed_at=now())  # 2h
    await insert_demand(session_factory, submitter, minutes_ago=240,
                        status="DONE", closed_at=now())  # 4h
    data = await board(session_factory)
    assert data["kpi"]["avgCycleHours"] == 3.0


@pytest.mark.asyncio
async def test_avg_cycle_hours_none_when_no_done(session_factory, submitter):
    await insert_demand(session_factory, submitter)
    data = await board(session_factory)
    assert data["kpi"]["avgCycleHours"] is None


# ---- 3. 趋势与分布 ----

@pytest.mark.asyncio
async def test_trend_12_weeks(session_factory, submitter):
    await insert_demand(session_factory, submitter)  # 本周
    await insert_demand(session_factory, submitter, minutes_ago=60 * 24 * 7)  # 上周
    await insert_demand(session_factory, submitter, status="DONE", closed_at=now())
    data = await board(session_factory)
    trend = data["trend"]
    assert len(trend) == 12
    monday = now().date() - timedelta(days=now().date().weekday())
    assert trend[-1]["weekStart"] == monday
    assert trend[-1]["newCnt"] == 2 and trend[-2]["newCnt"] == 1
    assert trend[-1]["doneCnt"] == 1


@pytest.mark.asyncio
async def test_type_and_channel_distribution(session_factory, submitter):
    await insert_demand(session_factory, submitter)
    await insert_demand(session_factory, submitter)
    await insert_demand(session_factory, submitter, demand_type_code="MATL", channel=None)
    await insert_demand(session_factory, submitter, minutes_ago=60 * 24 * 40)  # 上月不计
    data = await board(session_factory, "month")
    type_dist = {row["typeCode"]: row["cnt"] for row in data["typeDistribution"]}
    assert type_dist == {"TECH": 2, "MATL": 1}
    channel_dist = {row["channel"]: row["cnt"] for row in data["channelDistribution"]}
    assert channel_dist == {"CHUANGJIN_LS": 2, "未知": 1}


@pytest.mark.asyncio
async def test_dept_backlog_uses_submitter_dept(session_factory, submitter):
    await insert_demand(session_factory, submitter, submitter_dept="科技部")
    await insert_demand(session_factory, submitter, submitter_dept="科技部")
    await insert_demand(session_factory, submitter, submitter_dept=None)
    await insert_demand(session_factory, submitter, submitter_dept="财务部",
                        status="DONE", closed_at=now())  # 闭环不计
    data = await board(session_factory)
    assert data["deptBacklog"] == [{"dept": "科技部", "cnt": 2}, {"dept": "未填写", "cnt": 1}]


# ---- 4. SLA 健康度 ----

@pytest.mark.asyncio
async def test_sla_health_counts(session_factory, submitter):
    async with session_factory() as db:
        async with db.begin():
            db.add(SlaConfig(demand_type_code="TECH", status="SUBMITTED",
                             warn_minutes=60, max_minutes=120))
    await insert_demand(session_factory, submitter, minutes_ago=30)  # normal
    await insert_demand(session_factory, submitter, minutes_ago=70)  # warn
    await insert_demand(session_factory, submitter, minutes_ago=130)  # over
    await insert_demand(session_factory, submitter, minutes_ago=130,
                        demand_type_code="MATL")  # 无配置→normal
    await insert_demand(session_factory, submitter, minutes_ago=130,
                        hold_snapshot_status="SUBMITTED")  # 挂起豁免
    reset_id = await insert_demand(session_factory, submitter, minutes_ago=200)
    async with session_factory() as db:
        async with db.begin():
            db.add(DemandTransitionLog(
                demand_id=reset_id, from_status="ON_HOLD", to_status="SUBMITTED",
                event="RESUME", operator_id=submitter.id,
                created_at=now() - timedelta(minutes=10)))  # RESUME 新日志重置时钟
    health = (await board(session_factory))["slaHealth"]
    assert health == {"normal": 3, "warn": 1, "over": 1}


# ---- 5. 组织看板 ----

@pytest.mark.asyncio
async def test_org_board_counts(session_factory, submitter):
    await insert_demand(session_factory, submitter, status="SUBMITTED")
    await insert_demand(session_factory, submitter, status="SUBMITTED")
    await insert_demand(session_factory, submitter, status="TRIAGE")
    await insert_demand(session_factory, submitter, status="ANALYZING")
    await insert_demand(session_factory, submitter, status="ACCEPTANCE")
    await insert_demand(session_factory, submitter, status="DONE", closed_at=now())  # 本周
    await insert_demand(session_factory, submitter, minutes_ago=60 * 24 * 10,
                        status="DONE", closed_at=now() - timedelta(days=10))  # 非本周
    data = None
    async with session_factory() as db:
        data = await stat_service.org_board(db)
    assert data["pendingAccept"] == 2
    assert data["pool"] == 1
    assert data["processing"] == 2
    assert data["weekDone"] == 1


@pytest.mark.asyncio
async def test_member_workload_and_avg_inflight(session_factory, submitter):
    h1 = await make_user(session_factory, "处理一", "p4t-h1")
    h2 = await make_user(session_factory, "处理二", "p4t-h2")
    h3 = await make_user(session_factory, "处理三", "p4t-h3")
    d1 = await insert_demand(session_factory, submitter, status="IN_PROGRESS", assignee_id=h1.id)
    await insert_demand(session_factory, submitter, status="ANALYZING", assignee_id=h1.id)
    await insert_demand(session_factory, submitter, status="IN_PROGRESS", assignee_id=h2.id)
    async with session_factory() as db:
        async with db.begin():
            db.add(EffortLog(demand_id=d1, user_id=h1.id, hours=3.5, work_date=now().date()))
            db.add(EffortLog(demand_id=d1, user_id=h3.id, hours=1.0, work_date=now().date()))
            db.add(EffortLog(demand_id=d1, user_id=h2.id, hours=2.0,
                             work_date=now().date() - timedelta(days=40)))  # 超出 month 范围
    async with session_factory() as db:
        data = await stat_service.org_board(db, "month")
    assert data["avgInflightPerHandler"] == 1.5  # 3 在途 / 2 处理人
    workload = {row["userName"]: row for row in data["memberWorkload"]}
    assert workload["处理一"]["inflightCnt"] == 2 and workload["处理一"]["effortHours"] == 3.5
    assert workload["处理二"]["inflightCnt"] == 1 and workload["处理二"]["effortHours"] == 0.0
    assert workload["处理三"] == {"userId": h3.id, "userName": "处理三",
                                 "inflightCnt": 0, "effortHours": 1.0}
    assert data["memberWorkload"][0]["userName"] == "处理一"  # 按在途降序


# ---- 6. 当日快照刷新 ----

async def _snapshot_rows(factory):
    async with factory() as db:
        return (await db.execute(select(DemandStatDaily))).scalars().all()


@pytest.mark.asyncio
async def test_refresh_today_snapshot(session_factory, submitter):
    await insert_demand(session_factory, submitter)
    await insert_demand(session_factory, submitter)
    # 周期 2h：起止用同一基准成对传入，避免两次 now() 的毫秒差被 TIMESTAMPDIFF 截断成 119 分钟
    start = now() - timedelta(minutes=120)
    await insert_demand(session_factory, submitter, submitted_at=start,
                        status="DONE", closed_at=start + timedelta(minutes=120))
    await insert_demand(session_factory, submitter, demand_type_code="MATL",
                        status="DRAFT", submitted_at=None)
    async with session_factory() as db:
        async with db.begin():
            rows_written = await stat_service.refresh_today(db)
    assert rows_written == 3
    rows = {(r.demand_type_code, r.status): r for r in await _snapshot_rows(session_factory)}
    assert rows[("TECH", "SUBMITTED")].cnt == 2
    assert rows[("TECH", "SUBMITTED")].avg_cycle_hours is None
    assert float(rows[("TECH", "DONE")].avg_cycle_hours) == 2.0
    assert rows[("MATL", "DRAFT")].cnt == 1
    assert all(r.assignee_org_id == 0 and r.reporter_org_id == 0 for r in rows.values())
    # 幂等：重刷当日仍是 3 行
    async with session_factory() as db:
        async with db.begin():
            assert await stat_service.refresh_today(db) == 3
    assert len(await _snapshot_rows(session_factory)) == 3


@pytest.mark.asyncio
async def test_refresh_keeps_history_dates(session_factory, submitter):
    yesterday = now().date() - timedelta(days=1)
    async with session_factory() as db:
        async with db.begin():
            db.add(DemandStatDaily(stat_date=yesterday, demand_type_code="TECH", status="SUBMITTED",
                                   cnt=99))
    await insert_demand(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await stat_service.refresh_today(db)
    rows = await _snapshot_rows(session_factory)
    history = [r for r in rows if r.stat_date == yesterday]
    assert len(history) == 1 and history[0].cnt == 99  # 历史日期不回刷


@pytest.mark.asyncio
async def test_refresh_loop_start_stop(session_factory, monkeypatch):
    """后台刷新循环：受控 factory 注入跑一轮后干净关停（asyncio 先例，同 SLA）。"""
    import asyncio

    from app.db import session as db_session

    monkeypatch.setattr(db_session, "get_session_factory", lambda: session_factory)
    task, stop = stat_service.start_refresher(interval_seconds=3600)
    await asyncio.sleep(0.1)  # 让首轮刷新跑完（空表写 0 行，仅验证循环可跑可停）
    stop.set()
    await asyncio.wait_for(task, timeout=5)
    assert task.done()


# ---- 7. API 守卫 ----

async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_api_boards_role_guard(client, session_factory):
    await make_user(session_factory, "经理", "p4t-mgr", role="MANAGER")
    await make_user(session_factory, "管理者", "p4t-exec", role="EXECUTIVE")
    await make_user(session_factory, "处理人", "p4t-hdl")
    manager = await _login(client, "经理", "p4t-mgr")
    executive = await _login(client, "管理者", "p4t-exec")
    handler = await _login(client, "处理人", "p4t-hdl")
    # 成功断言一律查 body code==0（统一响应体：错误也走 HTTP 200）
    for path in ("/demandhub-api/dashboard/manager", "/demandhub-api/dashboard/org"):
        assert (await client.get(path, headers=manager)).json()["code"] == 0
        assert (await client.get(path, headers=executive)).json()["code"] == 0
        assert (await client.get(path, headers=handler)).json()["code"] == 403
    data = (await client.get("/demandhub-api/dashboard/manager", headers=manager)).json()["data"]
    assert set(data) == {"kpi", "trend", "typeDistribution", "channelDistribution",
                         "deptBacklog", "slaHealth"}
    assert set(data["kpi"]) == {"monthNew", "inflight", "done", "slaOver", "avgCycleHours"}


@pytest.mark.asyncio
async def test_api_stat_refresh_guard_and_run(client, session_factory, submitter):
    await make_user(session_factory, "经理", "p4t-mgr2", role="MANAGER")
    await make_user(session_factory, "管理者", "p4t-exec2", role="EXECUTIVE")
    manager = await _login(client, "经理", "p4t-mgr2")
    executive = await _login(client, "管理者", "p4t-exec2")
    admin = await _login(client, "超管", "mvp-admin")  # 企微白名单 ADMIN（过渡期）
    await insert_demand(session_factory, submitter)
    path = "/demandhub-api/dashboard/stat-refresh"
    assert (await client.post(path, headers=manager)).json()["code"] == 403
    result = (await client.post(path, headers=executive)).json()
    assert result["code"] == 0 and result["data"]["rows"] == 1
    assert (await client.post(path, headers=admin)).json()["code"] == 0  # ADMIN 直通


@pytest.mark.asyncio
async def test_api_custom_range_validation(client, session_factory):
    await make_user(session_factory, "经理", "p4t-mgr3", role="MANAGER")
    manager = await _login(client, "经理", "p4t-mgr3")
    base = "/demandhub-api/dashboard/manager"
    assert (await client.get(base, params={"range": "custom"}, headers=manager)).json()["code"] == 400
    assert (await client.get(base, params={"range": "year"}, headers=manager)).json()["code"] == 400
    ok_resp = await client.get(base, params={"range": "custom", "from": "2026-10-01", "to": "2026-10-14"},
                               headers=manager)
    assert ok_resp.json()["code"] == 0
