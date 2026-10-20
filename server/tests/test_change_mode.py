"""方案④（2026-10-11 口径显性化）：提报口径改判（轻量↔常规双向，提报人主动）。

链路：DRAFT/NEED_INFO 下 change_mode（origin=user 留痕 + modeChange 播报进上下文）
→ 提交门槛随口径切换（light 只拦 4 项最小集）→ AI 判定不得翻转用户手动口径。
边界：同口径拒绝；打回补充期间同样可切换（2026-10-20 拍板，口径由提报人自主判断）。
"""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.guide import GuideService
from app.agent.schemas import GuideChatRequest
from app.core.errors import BizError, ErrorCode
from app.db.models import AgentMessage, Demand, DemandChangeLog, User
from app.services import demand_service, session_service
from tests.test_guide import FakeArk

# 只含 light 最小集的表单：C/D 12 项模板大片缺失（换 logo 类微需求填不满模板的典型形态）
MINIMAL = {"title": "更换首页顶部logo", "demandTypeCode": "TECH",
           "content": "把系统首页顶部的logo换成新设计的蓝色版本", "urgency": "NORMAL",
           "elements": {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}}}


async def make_draft(factory, user, *, ext=None, session=False, elements=None):
    async with factory() as db:
        async with db.begin():
            payload = {"clientRequestId": f"change-mode-{uuid4().hex}", "fieldSources": {"demandTypeCode": "default"},
                       **MINIMAL}
            if elements is not None:
                payload["elements"] = elements
            if ext is not None:
                payload["ext"] = ext
            demand = await demand_service.create_draft(db, user, payload)
            if session:
                await session_service.create(db, user, "SUBMIT_GUIDE", demand.id)
    return demand.id


async def change_mode(factory, user, demand_id, level):
    async with factory() as db:
        async with db.begin():
            demand = await db.get(Demand, demand_id)
            return await demand_service.change_mode(db, user, demand_id, demand.revision, level)


async def get_demand(factory, demand_id):
    async with factory() as db:
        return await db.get(Demand, demand_id)


@pytest.mark.asyncio
async def test_change_mode_bidirectional_with_logs_and_notice(session_factory, user):
    """双向改判：origin=user 留痕、change_log 记 ext.mode、modeChange 播报注入会话。"""
    did = await make_draft(session_factory, user, session=True)
    # 默认 standard（无 mode）→ light
    light = await change_mode(session_factory, user, did, "light")
    assert light.ext["mode"] == {"level": "light", "evidence": "提报人手动调整提报口径", "origin": "user"}
    # light → standard（用户可再切回）
    standard = await change_mode(session_factory, user, did, "standard")
    assert standard.ext["mode"]["level"] == "standard" and standard.ext["mode"]["origin"] == "user"
    logs = []
    async with session_factory() as db:
        rows = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did,
            DemandChangeLog.field_key == "ext.mode").order_by(DemandChangeLog.id))).scalars().all()
        # old_value/new_value 为 JSON 列，SQLAlchemy 已解码为 dict（无需 json.loads）
        logs = [(row.old_value, row.new_value) for row in rows]
        notices = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == light.session_id,
            AgentMessage.structured_payload["kind"].as_string() == "modeChange"))).scalars().all()
    assert logs == [(None, {"level": "light", "evidence": "提报人手动调整提报口径", "origin": "user"}),
                    ({"level": "light", "evidence": "提报人手动调整提报口径", "origin": "user"},
                     {"level": "standard", "evidence": "提报人手动调整提报口径", "origin": "user"})]
    assert [notice.structured_payload["to"] for notice in notices] == ["light", "standard"]
    assert "常规提报」改为「轻量提报" in notices[0].content
    assert "轻量提报」改为「常规提报" in notices[1].content


@pytest.mark.asyncio
async def test_change_mode_rejects_same_level(session_factory, user):
    did = await make_draft(session_factory, user)
    with pytest.raises(BizError) as error:
        await change_mode(session_factory, user, did, "standard")  # 无 mode 缺省即 standard
    assert error.value.code == ErrorCode.PARAM_INVALID.code


@pytest.mark.asyncio
async def test_change_mode_allowed_during_return(session_factory, user):
    """打回补充期间可切轻量（2026-10-20 拍板）：打回不锁口径，standard 切 light 放行，
    重提按 light 4 项门槛校验。"""
    full = {"A": {"techSubtype": "SYS_DEV"},
            "C": {"userRole": "访问系统首页的零售客户", "userGoal": "看到品牌新形象",
                  "useScenario": "客户打开系统首页浏览", "painPoint": "旧logo风格过时"},
            "D": {"functionDescription": "替换首页顶部logo", "inputOutput": "输入新logo资源，输出更新后首页",
                  "acceptanceCriteria": "首页顶部展示新logo"}}
    did = await make_draft(session_factory, user, elements=full)
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            await demand_service.submit(db, user, did, demand.revision)
    async with session_factory() as db:
        async with db.begin():
            # P2 起打回走状态机 RETURN 事件（roles=ADMIN）：需真实管理员操作
            admin = User(name="管理员", wecom_userid=f"cm-admin-{uuid4().hex[:8]}",
                         channel="CHUANGJIN_LS", role="ADMIN")
            db.add(admin)
            await db.flush()
            await demand_service.return_demand(db, admin, did, "请补充使用场景")
    light = await change_mode(session_factory, user, did, "light")
    assert light.ext["mode"]["level"] == "light" and light.ext["returnReason"]["reason"] == "请补充使用场景"


@pytest.mark.asyncio
async def test_light_gate_after_manual_downgrade(session_factory, user):
    """常规→轻量降级后提交走 4 项门槛：C/D 大片缺失不再拦截，已填的期望效果保留。"""
    did = await make_draft(session_factory, user)
    light = await change_mode(session_factory, user, did, "light")
    async with session_factory() as db:
        async with db.begin():
            submitted = await demand_service.submit(db, user, did, light.revision)
    assert submitted.status == "SUBMITTED" and submitted.demand_no.startswith("TECH-")


@pytest.mark.asyncio
async def test_standard_gate_after_manual_upgrade(session_factory, user):
    """轻量→常规升级后提交走 12 项门槛：C/D 缺口重新拦截。"""
    did = await make_draft(session_factory, user, ext={"mode": {"level": "light", "evidence": "换logo"}})
    standard = await change_mode(session_factory, user, did, "standard")
    async with session_factory() as db:
        with pytest.raises(BizError) as error:
            async with db.begin():
                await demand_service.submit(db, user, did, standard.revision)
    assert error.value.code == ErrorCode.PARAM_INVALID.code and "未填写" in str(error.value)


@pytest.mark.asyncio
async def test_user_mode_not_flipped_by_agent(session_factory, user):
    """AI 不得翻转用户手动口径：用户降级 light 后，模型再判 standard 也不生效（origin=user 双向粘性）。"""
    did = await make_draft(session_factory, user, session=True)
    light = await change_mode(session_factory, user, did, "light")
    fake = FakeArk({"structured": {}, "elements": [], "modeSignal": {"level": "standard", "evidence": "模型又觉得不小"}})
    async with session_factory() as db:
        req = GuideChatRequest(demandId=did, sessionId=light.session_id, revision=light.revision,
                               requestId="change-mode-c1", message="就换个logo，别的都不用动")
        result = await GuideService(db, user, fake).execute(req)
    assert result.mode["level"] == "light" and result.mode["origin"] == "user"
    # 口径改判播报不参与质量快照回放：不产生「表单已被覆盖」类异常，对话链路正常放行
    demand = await get_demand(session_factory, did)
    assert demand.ext["mode"]["level"] == "light"


@pytest.mark.asyncio
async def test_change_mode_api_flow(client, session_factory, user):
    """API 层：改判 200 + 响应带新 ext.mode；revision 不匹配 409。"""
    did = await make_draft(session_factory, user)
    token = (await client.post("/demandhub-api/auth/dev-login",
        json={"name": "测试用户", "wecomUserid": "test-user"})).json()["data"]["accessToken"]
    response = await client.post(f"/demandhub-api/demand/{did}/mode",
        json={"expectedRevision": 0, "level": "light"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["ext"]["mode"]["level"] == "light" and data["revision"] == 1
    stale = await client.post(f"/demandhub-api/demand/{did}/mode",
        json={"expectedRevision": 0, "level": "standard"}, headers={"Authorization": f"Bearer {token}"})
    # 统一响应体：BizError 走 HTTP 200 + body 业务码（409 版本冲突）
    assert stale.json()["code"] == ErrorCode.CONFLICT.code


async def last_messages(factory, session_id, count):
    async with factory() as db:
        rows = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == session_id)
                                 .order_by(AgentMessage.id))).scalars().all()
    return list(rows)[-count:]


@pytest.mark.asyncio
async def test_change_mode_follows_up_with_new_mode_snapshot(session_factory, user):
    """口径改判当场接续（2026-10-20 拍板）：播报后紧跟一条按新口径重算的正式快照——
    升 standard：C/D 缺口立即可见并开口追问；降 light：最小集齐直接出「确认提交」。"""
    did = await make_draft(session_factory, user, session=True)  # MINIMAL：仅 light 最小集
    await change_mode(session_factory, user, did, "light")  # 先降 light 建立起点
    upgraded = await change_mode(session_factory, user, did, "standard")
    notice, snapshot = await last_messages(session_factory, upgraded.session_id, 2)
    assert notice.structured_payload["kind"] == "modeChange"
    payload = snapshot.structured_payload
    assert payload.get("kind") is None  # 无 kind = 正式快照，参与前端质量卡回放
    assert payload["revision"] == upgraded.revision
    assert payload["canSubmit"] is False and payload["askedTarget"] is not None
    # 切回 light：最小集齐 → 快照直接可提交
    light = await change_mode(session_factory, user, did, "light")
    latest = (await last_messages(session_factory, light.session_id, 1))[0].structured_payload
    assert latest.get("kind") is None and latest["canSubmit"] is True


# 归类改判（2026-10-20 拍板）：与手改要素/口径改判同规则——当场 typeChange 播报 + 按新归类重算快照
FULL_NO_B = {"A": {"techSubtype": "SYS_DEV"},
             "C": {"userRole": "零售客户", "userGoal": "看到新logo", "useScenario": "打开系统首页浏览", "painPoint": "旧logo风格过时"},
             "D": {"functionDescription": "替换首页顶部logo", "inputOutput": "输入新logo资源，输出更新后首页",
                   "acceptanceCriteria": "首页顶部展示新logo"}}


@pytest.mark.asyncio
async def test_type_confirm_follows_up_with_business_gate(session_factory, user):
    """确认业务需求 → B 区纳入必填：typeChange 播报 + 接续快照按新门槛拦截并追问 B 区；
    恢复 AI 判断 → B 区门槛解除，A/C/D 齐备直接可提交。"""
    did = await make_draft(session_factory, user, session=True, elements=FULL_NO_B)
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            await demand_service.update_draft(db, user, did,
                {"ext": {"typeRecognition": {"confirmed": "business"}}, "expectedRevision": demand.revision})
    demand = await get_demand(session_factory, did)
    notice, snapshot = await last_messages(session_factory, demand.session_id, 2)
    assert notice.structured_payload["kind"] == "typeChange"
    assert "业务需求" in notice.content and "纳入必填" in notice.content
    payload = snapshot.structured_payload
    assert payload.get("kind") is None and payload["canSubmit"] is False and payload["askedTarget"] is not None
    # 恢复 AI 判断：B 区不再必填 → A/C/D 齐备直接出「确认提交」
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            await demand_service.update_draft(db, user, did,
                {"ext": {"typeRecognition": {"confirmed": None}}, "expectedRevision": demand.revision})
    demand = await get_demand(session_factory, did)
    notice, snapshot = await last_messages(session_factory, demand.session_id, 2)
    assert notice.structured_payload["kind"] == "typeChange" and "恢复由 AI 自动判断" in notice.content
    assert snapshot.structured_payload["canSubmit"] is True


@pytest.mark.asyncio
async def test_type_confirm_unchanged_stays_silent(session_factory, user):
    """归类未变化不播报：整表单回传带原样 typeRecognition 不产生 typeChange 消息。"""
    recognition = {"judgedType": "function", "confirmed": "function"}
    did = await make_draft(session_factory, user, session=True, ext={"typeRecognition": dict(recognition)})
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            await demand_service.update_draft(db, user, did,
                {"ext": {"typeRecognition": dict(recognition)}, "expectedRevision": demand.revision})
    demand = await get_demand(session_factory, did)
    async with session_factory() as db:
        notices = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == demand.session_id,
            AgentMessage.structured_payload["kind"].as_string() == "typeChange"))).scalars().all()
    assert notices == []
