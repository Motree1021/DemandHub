"""概述后台重写（FR-06 手改联动）：锁内串行、失败静默、不加 revision、无消息无留痕；手工路径忽略 overview。"""
import asyncio
import json

from app.agent import overview
from app.db.models import Demand, User
from app.services import demand_service, session_service
from tests.test_guide import FakeArk


def _overview_output():
    return {"problem": "手工拼表每次40分钟易错｜现有统计方式低效",
            "userScene": "客户经理每天晨会前统计渠道销量｜晨会前手工统计",
            "goal": "每天早上8点前自动生成销量报表｜自动报表替代手工",
            "acceptance": "交易日8:00前生成且数据一致｜按时生成数据一致"}


async def _draft(session_factory, user, key):
    async with session_factory() as db:
        async with db.begin():
            d = await demand_service.create_draft(db, user, {"clientRequestId": key, "demandTypeCode": "TECH",
                "title": "语音播报优化", "content": "整理需求",
                "elements": {"C": {"userRole": "客户经理", "painPoint": "手工拼表每次40分钟"},
                             "D": {"acceptanceCriteria": "连续7天对账误差为0"}}})
            session = await session_service.create(db, user, "SUBMIT_GUIDE", d.id)
            return d.id, session.id


async def _demand_ext(session_factory, demand_id):
    from app.db.models import Demand
    async with session_factory() as db:
        demand = await db.get(Demand, demand_id)
        return demand


async def test_rewrite_overview_updates_ext_without_revision_or_noise(session_factory, user):
    demand_id, session_id = await _draft(session_factory, user, "ov-rewrite")
    fake = FakeArk(output=_overview_output())
    await overview.rewrite_overview(demand_id, user.id, fake)
    assert fake.repairs == 1  # FakeArk.complete_json 计入 repairs
    demand = await _demand_ext(session_factory, demand_id)
    assert demand.ext["overview"]["problem"].startswith("手工拼表")
    assert demand.field_sources["ext.overview"] == "agent"
    # 不加 revision、不写聊天消息、不写留痕
    assert demand.revision == 0
    from sqlalchemy import func, select

    from app.db.models import AgentMessage, DemandChangeLog
    async with session_factory() as db:
        assert (await db.execute(select(func.count()).select_from(DemandChangeLog))).scalar_one() == 0
        assert (await db.execute(select(func.count()).select_from(AgentMessage)
                                 .where(AgentMessage.session_id == session_id))).scalar_one() == 0


async def test_rewrite_skipped_when_ai_unavailable_or_model_fails(session_factory, user):
    demand_id, _ = await _draft(session_factory, user, "ov-skip")
    from app.agent.llm_client import LlmUnavailable
    # 冷却中：直接跳过，不调用模型
    cooling = FakeArk(output=_overview_output())
    cooling.cooldown_until = float("inf")
    await overview.rewrite_overview(demand_id, user.id, cooling)
    assert cooling.repairs == 0
    assert (await _demand_ext(session_factory, demand_id)).ext.get("overview") is None
    # 模型调用失败：保留旧概述、不抛错
    failing = FakeArk(output=_overview_output())

    async def fail(_messages):
        raise LlmUnavailable
    failing.complete_json = fail
    await overview.rewrite_overview(demand_id, user.id, failing)
    assert (await _demand_ext(session_factory, demand_id)).ext.get("overview") is None


async def test_rewrite_ignores_bad_output_keeps_four_keys_only(session_factory, user):
    demand_id, _ = await _draft(session_factory, user, "ov-parse")
    # 非法输出（非 JSON / 全空 / 仅杂键与空白段）均不写
    for raw in ("不是JSON", "{}", json.dumps({"extra": "x", "problem": "  "})):
        fake = FakeArk(output=raw)
        await overview.rewrite_overview(demand_id, user.id, fake)
        assert (await _demand_ext(session_factory, demand_id)).ext.get("overview") is None
    # 合法输出只保留四键、剔除空白段与白名单外键
    fake = FakeArk(output={**_overview_output(), "extra": "x", "acceptance": "  "})
    await overview.rewrite_overview(demand_id, user.id, fake)
    demand = await _demand_ext(session_factory, demand_id)
    assert set(demand.ext["overview"]) == {"problem", "userScene", "goal"}


async def test_rewrite_skips_submitted_or_foreign_draft(session_factory, user):
    demand_id, _ = await _draft(session_factory, user, "ov-state")
    fake = FakeArk(output=_overview_output())
    from sqlalchemy import update
    async with session_factory() as db:
        async with db.begin():
            # 直接置 SUBMITTED：submit 接口需全量必填校验，与本用例关注的守卫无关
            await db.execute(update(Demand).where(Demand.id == demand_id).values(status="SUBMITTED"))
    await overview.rewrite_overview(demand_id, user.id, fake)
    assert fake.repairs == 0  # 读阶段即发现非 DRAFT，未调用模型
    # 他人草稿：同样跳过
    async with session_factory() as db:
        async with db.begin():
            other = User(name="他人", wecom_userid="ov-other", channel="CHUANGJIN_LS")
            db.add(other)
            await db.flush()
            d2 = await demand_service.create_draft(db, other, {"clientRequestId": "ov-other-draft",
                "demandTypeCode": "TECH", "title": "他人草稿", "content": "x"})
            other_id = d2.id
    await overview.rewrite_overview(other_id, user.id, fake)
    assert fake.repairs == 0
    assert (await _demand_ext(session_factory, other_id)).ext.get("overview") is None


async def test_schedule_serializes_concurrent_rewrites(monkeypatch):
    # 同一草稿连续排两个后台任务：串行执行，第一个未完成时第二个被锁挡住
    order = []
    release = asyncio.Event()

    async def fake_rewrite(demand_id, user_id):
        order.append(("start", demand_id))
        if demand_id == 111:
            await release.wait()
        order.append(("end", demand_id))

    monkeypatch.setattr(overview, "rewrite_overview", fake_rewrite)
    overview.schedule_overview_rewrite(111, 1)
    await asyncio.sleep(0.01)
    overview.schedule_overview_rewrite(111, 2)
    await asyncio.sleep(0.01)
    assert order == [("start", 111)]  # 第二个任务在锁上等待
    release.set()
    await asyncio.sleep(0.02)
    assert order == [("start", 111), ("end", 111), ("start", 111), ("end", 111)]


async def test_schedule_swallows_task_errors(monkeypatch):
    # 后台任务异常不外泄：保存动作的响应不受影响
    ran = []

    async def fake_rewrite(demand_id, user_id):
        ran.append((demand_id, user_id))
        raise RuntimeError("模拟概述重写崩溃")

    monkeypatch.setattr(overview, "rewrite_overview", fake_rewrite)
    overview.schedule_overview_rewrite(123, 1)
    await asyncio.sleep(0.05)
    assert ran == [(123, 1)]  # 执行过、且异常被吞掉（测试本身不因异常失败）


async def test_manual_update_ignores_client_overview(session_factory, user):
    # 手工保存回传的旧概述被忽略：防止覆盖后台重写的新概述
    demand_id, _ = await _draft(session_factory, user, "ov-ignore")
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, demand_id, {"expectedRevision": 0,
                "ext": {"overview": {"problem": "客户端带来的旧概述"}}})
    demand = await _demand_ext(session_factory, demand_id)
    assert demand.ext.get("overview") is None
    # 已有概述的草稿：手工回传旧值不回滚 AI 已写的概述（第一次 update 已把 revision 加到 1）
    fake = FakeArk(output=_overview_output())
    await overview.rewrite_overview(demand_id, user.id, fake)
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, demand_id, {"expectedRevision": 1,
                "ext": {"overview": {"problem": "客户端带来的旧概述"}}})
    assert (await _demand_ext(session_factory, demand_id)).ext["overview"]["problem"].startswith("手工拼表")


async def test_api_schedules_rewrite_only_for_manual_change(client, auth_headers, session_factory, monkeypatch):
    # API 集成：notifyChanges 才触发后台重写；AI 链路与其余保存不触发。
    # user id 从库里查（dev-login 已建 test-user，再用 user fixture 会唯一键冲突）
    from sqlalchemy import select
    async with session_factory() as db:
        user_id = (await db.execute(select(User.id).where(User.wecom_userid == "test-user"))).scalar_one()
    scheduled = []
    monkeypatch.setattr("app.api.demand.schedule_overview_rewrite",
                        lambda demand_id, uid: scheduled.append((demand_id, uid)))
    draft = (await client.post("/demandhub-api/demand", headers=auth_headers,
        json={"clientRequestId": "ov-api", "demandTypeCode": "TECH", "title": "标题", "content": "内容"})).json()["data"]
    # 无 notifyChanges 的保存（先保存草稿按钮）：不触发
    saved = (await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
                     json={"expectedRevision": draft["revision"], "title": "新标题"})).json()["data"]
    assert scheduled == []
    # 手工改要素（notifyChanges=true）：提交后触发（用第一次保存返回的最新 revision）
    updated = (await client.put(f"/demandhub-api/demand/{draft['id']}", headers=auth_headers,
        json={"expectedRevision": saved["revision"], "title": "再次改", "notifyChanges": True})).json()["data"]
    assert scheduled == [(updated["id"], user_id)]
