"""阶段三（2026-10-11 方案③）：NEED_INFO 打回闭环。

链路：SUBMITTED --ADMIN 打回（带原因、change_log 留痕、mode 升 standard、会话重开+播报）--> NEED_INFO
补填（对话/表单同 DRAFT 可编辑）--> 重提（保留编号、清 returnReason、状态留痕）--> SUBMITTED
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.guide import GuideService
from app.agent.schemas import GuideChatRequest
from app.core.errors import BizError, ErrorCode
from app.db.models import AgentMessage, AgentSession, Demand, DemandChangeLog, User
from app.services import demand_service, session_service
from tests.test_guide import FakeArk

ACD = {"A": {"techSubtype": "DATA_RPT"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
             "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
       "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}

RETURN_REASON = "缺少使用场景和数据来源说明，请补充后再提交"


async def make_submitted(factory, user, *, elements=None, ext=None, session=False):
    """建草稿→建会话（可选）→提交，返回 (demand_id, revision, demand_no)。"""
    async with factory() as db:
        async with db.begin():
            payload = {
                "clientRequestId": f"need-info-{uuid4().hex}",
                "title": "晨会持仓报表", "demandTypeCode": "TECH",
                "content": "机构业务部客户经理每天晨会前查看持仓汇总", "urgency": "NORMAL",
                "elements": elements if elements is not None else ACD,
                "fieldSources": {"demandTypeCode": "default"}}
            if ext is not None:
                payload["ext"] = ext
            demand = await demand_service.create_draft(db, user, payload)
            if session:
                await session_service.create(db, user, "SUBMIT_GUIDE", demand.id)
            submitted = await demand_service.submit(db, user, demand.id, demand.revision)
            return submitted.id, submitted.revision, submitted.demand_no


@pytest.fixture
async def admin(session_factory):
    """P2 起打回走状态机 RETURN 事件（roles=ADMIN）：服务层调用须传真实管理员。"""
    async with session_factory() as db:
        async with db.begin():
            user = User(name="管理员", wecom_userid="p0-admin", channel="CHUANGJIN_LS", role="ADMIN")
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def admin_return(factory, admin_user, demand_id):
    async with factory() as db:
        async with db.begin():
            return await demand_service.return_demand(db, admin_user, demand_id, RETURN_REASON)


async def get_demand(factory, demand_id):
    async with factory() as db:
        return await db.get(Demand, demand_id)


@pytest.mark.asyncio
async def test_return_requires_submitted(session_factory, user, admin):
    did, rev, _ = await make_submitted(session_factory, user)
    async with session_factory() as db:
        async with db.begin():
            await demand_service.close(db, user, did, "撤销")  # CLOSED 不可打回
    with pytest.raises(BizError) as error:
        await admin_return(session_factory, admin, did)
    assert error.value.code == ErrorCode.ILLEGAL_STATE_TRANSITION.code


@pytest.mark.asyncio
async def test_admin_return_writes_reason_logs_and_locks_standard(session_factory, user, admin):
    """打回四件套：状态流转+原因留痕（change_log 两行）+mode 升 standard（轻量需求不得回快速通道）+编号保留。"""
    did, rev, demand_no = await make_submitted(session_factory, user, session=True)
    # 预置轻量模式：打回后必须升 standard
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            demand.ext = {**demand.ext, "mode": {"level": "light", "evidence": "换logo"}}
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    assert demand.status == "NEED_INFO" and demand.demand_no == demand_no  # 编号保留：管理员按编号跟踪
    assert demand.ext["returnReason"]["reason"] == RETURN_REASON
    assert demand.ext["mode"]["level"] == "standard"  # 打回后按 12 项完整口径补填
    async with session_factory() as db:
        logs = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did).order_by(DemandChangeLog.id))).scalars().all()
    returned = [log for log in logs if log.source == "admin"]
    assert [(log.field_key, log.old_value, log.new_value) for log in returned] == [
        ("status", "SUBMITTED", "NEED_INFO"),
        ("ext.returnReason", None, json.loads(json.dumps(demand.ext["returnReason"], ensure_ascii=False)))]


@pytest.mark.asyncio
async def test_return_reopens_session_and_appends_notice(session_factory, user, admin):
    """会话重开 ACTIVE + 注入引述打回原因的播报（kind=returnNotice，不参与质量快照回放）。"""
    did, rev, _ = await make_submitted(session_factory, user, session=True)
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        session_id = demand.session_id
        assert (await db.get(AgentSession, session_id)).status == "CLOSED"  # 提交后会话关闭
    await admin_return(session_factory, admin, did)
    async with session_factory() as db:
        assert (await db.get(AgentSession, session_id)).status == "ACTIVE"
        notice = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == session_id,
            AgentMessage.structured_payload["kind"].as_string() == "returnNotice"))).scalar_one()
    assert RETURN_REASON in notice.content
    assert "补充" in notice.content


@pytest.mark.asyncio
async def test_return_without_session_is_fine(session_factory, user, admin):
    """无会话的直报需求打回不炸：补填入口由表单/新建会话兜底。"""
    did, rev, _ = await make_submitted(session_factory, user, session=False)
    await admin_return(session_factory, admin, did)
    assert (await get_demand(session_factory, did)).status == "NEED_INFO"


@pytest.mark.asyncio
async def test_need_info_resubmit_flow(session_factory, user, admin):
    """打回→对话补填（AI 链路放行）→重提：清 returnReason、写状态留痕、保留编号、会话关闭。"""
    did, rev, demand_no = await make_submitted(session_factory, user, session=True)
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    rev = demand.revision
    # NEED_INFO 下打回播报不参与快照回放，对话链路正常放行：AI 引述打回原因后补齐 C 区缺口
    fake = FakeArk({"structured": {"elements": {"C": {"useFrequency": "每个交易日"}}}, "elements": [],
                    "modeSignal": {"level": "standard", "evidence": "打回补填"}})
    async with session_factory() as db:
        req = GuideChatRequest(demandId=did, sessionId=demand.session_id, revision=rev, requestId="need-info-c1", message="每天早上都用")
        result = await GuideService(db, user, fake).execute(req)
    assert result.mode["level"] == "standard"
    # AI 回复模板前置白话引述打回原因（模型自述不可靠，引述由 policy 层保证）
    assert "打回原因" in result.reply and RETURN_REASON in result.reply
    demand = await get_demand(session_factory, did)
    assert demand.elements["C"]["useFrequency"] == "每个交易日"
    # 表单直改（H5 卡片编辑）在 NEED_INFO 下同样放行，且不能篡改打回原因
    async with session_factory() as db:
        async with db.begin():
            await demand_service.update_draft(db, user, did, {"expectedRevision": demand.revision,
                "ext": {"returnReason": {"reason": "伪造的原因"}, "typeRecognition": {"confirmed": "function"}}})
    demand = await get_demand(session_factory, did)
    assert demand.ext["returnReason"]["reason"] == RETURN_REASON
    assert demand.ext["typeRecognition"]["confirmed"] == "function"
    # 重提成功：returnReason 清除 + 状态留痕 + 编号保留 + 会话关闭
    async with session_factory() as db:
        async with db.begin():
            resubmitted = await demand_service.submit(db, user, did, demand.revision)
    assert resubmitted.status == "SUBMITTED" and resubmitted.demand_no == demand_no
    assert "returnReason" not in resubmitted.ext
    async with session_factory() as db:
        logs = (await db.execute(select(DemandChangeLog).where(DemandChangeLog.demand_id == did,
            DemandChangeLog.field_key == "status").order_by(DemandChangeLog.id))).scalars().all()
        assert (logs[-1].old_value, logs[-1].new_value) == ("NEED_INFO", "SUBMITTED")
        assert (await db.get(AgentSession, demand.session_id)).status == "CLOSED"


@pytest.mark.asyncio
async def test_light_demand_return_resubmit_blocked_by_full_gate(session_factory, user, admin):
    """轻量需求打回后按 12 项完整口径：最小集齐也不放行，C/D 缺口重新拦截。"""
    light = {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}}
    did, rev, _ = await make_submitted(session_factory, user, elements=light,
                                        ext={"mode": {"level": "light", "evidence": "换logo微调"}})
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    async with session_factory() as db:
        with pytest.raises(Exception) as error:
            async with db.begin():
                await demand_service.submit(db, user, did, demand.revision)
        assert error.value.code == 400 and "未填写" in str(error.value)


@pytest.mark.asyncio
async def test_need_info_can_close(session_factory, user, admin):
    did, rev, _ = await make_submitted(session_factory, user)
    await admin_return(session_factory, admin, did)
    await get_demand(session_factory, did)
    async with session_factory() as db:
        async with db.begin():
            closed = await demand_service.close(db, user, did, "不提了")
    assert closed.status == "CLOSED" and closed.close_reason == "不提了"


@pytest.mark.asyncio
async def test_return_api_admin_gate_and_flow(client, session_factory, user):
    """API 层：普通用户 403，管理员 200；列表状态筛选含 NEED_INFO。"""
    did, rev, _ = await make_submitted(session_factory, user, session=True)
    user_token = (await client.post("/demandhub-api/auth/dev-login",
        json={"name": "测试用户", "wecomUserid": "test-user"})).json()["data"]["accessToken"]
    response = await client.post(f"/demandhub-api/admin/demand/{did}/return",
        json={"reason": RETURN_REASON}, headers={"Authorization": f"Bearer {user_token}"})
    # 统一响应体：BizError 走 HTTP 200 + body 业务码（403 无权限）
    assert response.json()["code"] == 403
    admin_token = (await client.post("/demandhub-api/auth/dev-login",
        json={"name": "管理员", "wecomUserid": "mvp-admin"})).json()["data"]["accessToken"]
    response = await client.post(f"/demandhub-api/admin/demand/{did}/return",
        json={"reason": RETURN_REASON}, headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "NEED_INFO" and data["ext"]["returnReason"]["reason"] == RETURN_REASON
    # 提报人列表「待补充」筛选可查到
    mine = (await client.get("/demandhub-api/demand/my", params={"status": "NEED_INFO"},
        headers={"Authorization": f"Bearer {user_token}"})).json()["data"]
    assert mine["total"] == 1 and mine["records"][0]["id"] == did
