"""阶段三（2026-10-11 方案③）：NEED_INFO 打回闭环。

链路：SUBMITTED --ADMIN 打回（带原因、change_log 留痕、会话重开+播报）--> NEED_INFO
补填（对话/表单同 DRAFT 可编辑）--> 重提（保留编号、清 returnReason、状态留痕）--> SUBMITTED
2026-10-20 拍板：打回不再强制升 standard，提报口径保持原样，轻量仍按 4 项最小集补填。
"""
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.agent.guide import GuideService
from app.agent.schemas import GuideChatRequest
from app.core.errors import BizError, ErrorCode
from app.db.models import (
    AgentMessage,
    AgentSession,
    Demand,
    DemandChangeLog,
    NotificationTemplate,
    User,
)
from app.services import demand_service, notification_service, session_service
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
async def test_admin_return_writes_reason_logs_and_keeps_mode(session_factory, user, admin):
    """打回三件套：状态流转+原因留痕（change_log 两行）+编号保留；
    提报口径保持原样（2026-10-20 拍板）：轻量需求打回后仍是轻量，按 4 项最小集补填。"""
    did, rev, demand_no = await make_submitted(session_factory, user, session=True)
    # 预置轻量模式：打回后必须原样保留
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            demand.ext = {**demand.ext, "mode": {"level": "light", "evidence": "换logo"}}
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    assert demand.status == "NEED_INFO" and demand.demand_no == demand_no  # 编号保留：管理员按编号跟踪
    assert demand.ext["returnReason"]["reason"] == RETURN_REASON
    assert demand.ext["mode"]["level"] == "light"  # 口径保持原样，不再强制升 standard
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
async def test_return_injects_opening_snapshot(session_factory, user, admin):
    """打回开场快照（2026-10-20 拍板方案A + 当日收敛拍板）：打回注入一条正式对话结果消息——无 kind（前端可回放）、
    带打回后 revision（回放守卫通过）；打回原因已由紧邻的 returnNotice 完整告知，开场快照不再重复引述，
    只给简短行动指引。修复重进提报页按钮/清单/步骤全丢的断链。"""
    did, rev, _ = await make_submitted(session_factory, user, session=True)
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    async with session_factory() as db:
        rows = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == demand.session_id)
                                 .order_by(AgentMessage.id.asc()))).scalars().all()
        agent_session = await db.get(AgentSession, demand.session_id)
    last, notice = rows[-1], rows[-2]
    payload = last.structured_payload
    assert payload.get("kind") is None  # 正式对话结果消息（非播报卡），前端 isReplayablePayload 认
    assert payload["revision"] == demand.revision  # 与打回后草稿同 revision，前端回放守卫不再误杀
    # 打回原因只在 returnNotice 里完整告知，快照不再前置引述，只给简短重提指引
    assert not payload["reply"].startswith("这条需求之前被打回过")
    assert "确认提交" in payload["reply"]
    assert (notice.structured_payload or {}).get("kind") == "returnNotice" and RETURN_REASON in notice.content
    # 要素已齐（打回原因与要素无关）：canSubmit=True，重进即见「确认提交」；asked_target 已同步
    assert payload["canSubmit"] is True and payload["askedTarget"] is None
    assert agent_session.asked_target is None


@pytest.mark.asyncio
async def test_return_snapshot_follows_original_mode(session_factory, user, admin):
    """打回快照按原口径（2026-10-20 拍板）：轻量需求打回后不升 standard，
    仍按 4 项最小集判断——最小集齐则 canSubmit=True，重进即见「确认提交」。"""
    elements = {"A": {"techSubtype": "DATA_RPT"}, "D": {"acceptanceCriteria": "连续7天与核心系统对账误差为0"}}
    ext = {"mode": {"level": "light", "evidence": "小改动"}}
    did, rev, _ = await make_submitted(session_factory, user, elements=elements, ext=ext, session=True)
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    assert demand.ext["mode"]["level"] == "light"  # 口径保持原样
    async with session_factory() as db:
        last = (await db.execute(select(AgentMessage).where(AgentMessage.session_id == demand.session_id)
                                 .order_by(AgentMessage.id.desc()))).scalars().first()
    payload = last.structured_payload
    assert payload["canSubmit"] is True and payload["askedTarget"] is None  # light 最小集齐
    assert "确认提交" in payload["reply"]
    assert not payload["reply"].startswith("这条需求之前被打回过")  # returnNotice 已告知，不重复引述


@pytest.mark.asyncio
async def test_detail_self_heals_legacy_returned_demand(session_factory, user, admin):
    """存量打回单自愈（2026-10-20 拍板）：修复上线前被打回的单（会话里无匹配 revision 的开场快照），
    读取详情时自动补注——重进提报页按钮/清单一次就位；幂等，重复读取不重复注入。"""
    did, rev, _ = await make_submitted(session_factory, user, session=True)
    # 模拟存量：直接落到 NEED_INFO（状态机流转 bump revision），不注入任何消息
    async with session_factory() as db:
        async with db.begin():
            demand = await db.get(Demand, did)
            demand.status = "NEED_INFO"
            demand.ext = {**(demand.ext or {}),
                          "returnReason": {"reason": "请补充附件后重新提交", "by": "管理员", "at": "2026-10-20T00:00:00+00:00"}}
            demand.revision += 1
    async with session_factory() as db:
        async with db.begin():
            result = await demand_service.detail(db, user, did)
    payloads = [json.loads(m["structuredPayload"]) for m in result["messages"] if m["structuredPayload"]]
    snap = payloads[-1]
    demand = await get_demand(session_factory, did)
    assert snap.get("kind") is None and snap["revision"] == demand.revision
    assert snap["canSubmit"] is True  # 要素齐备（打回原因只是补附件）→ 重进即见「确认提交」
    assert snap["reply"].startswith("这条需求之前被打回过") and "请补充附件后重新提交" in snap["reply"]
    # 幂等：再次读取命中既有快照，不再注入
    async with session_factory() as db:
        async with db.begin():
            again = await demand_service.detail(db, user, did)
    assert len(again["messages"]) == len(result["messages"])


def _draft_payload(key, elements):
    return {"clientRequestId": key, "title": "晨会持仓报表", "demandTypeCode": "TECH",
            "content": "客户经理每天晨会前查各机构持仓", "urgency": "NORMAL", "elements": elements}


@pytest.mark.asyncio
async def test_draft_entry_self_heals_missing_snapshot(session_factory, user):
    """草稿续提进入即校验（2026-10-20 拍板）：无任何快照的草稿（手改/老路径顶了 revision 或老草稿），
    读取详情时纯规则补注——要素齐备 → canSubmit=True，进页直接显示「确认提交」；幂等。"""
    async with session_factory() as db:
        async with db.begin():
            draft = await demand_service.create_draft(db, user, _draft_payload("heal-draft", ACD))
            await session_service.create(db, user, "SUBMIT_GUIDE", draft.id)
            did = draft.id
    async with session_factory() as db:
        async with db.begin():
            result = await demand_service.detail(db, user, did)
    payloads = [json.loads(m["structuredPayload"]) for m in result["messages"] if m["structuredPayload"]]
    snap = payloads[-1]
    draft = await get_demand(session_factory, did)
    assert snap.get("kind") is None and snap["revision"] == draft.revision
    assert snap["canSubmit"] is True
    # 幂等：再次读取不重复注入
    async with session_factory() as db:
        async with db.begin():
            again = await demand_service.detail(db, user, did)
    assert len(again["messages"]) == len(result["messages"])


@pytest.mark.asyncio
async def test_draft_entry_snapshot_points_at_gap(session_factory, user):
    """草稿续提进入即校验（2026-10-20 拍板）：要素有缺口时注入的快照选中当前缺口追问，canSubmit=False。"""
    async with session_factory() as db:
        async with db.begin():
            draft = await demand_service.create_draft(db, user, _draft_payload("heal-gap", {"A": {"techSubtype": "DATA_RPT"}}))
            await session_service.create(db, user, "SUBMIT_GUIDE", draft.id)
            did = draft.id
    async with session_factory() as db:
        async with db.begin():
            result = await demand_service.detail(db, user, did)
    snap = json.loads(result["messages"][-1]["structuredPayload"])
    assert snap["canSubmit"] is False and snap["askedTarget"] is not None


@pytest.mark.asyncio
async def test_stale_template_snapshot_triggers_recompute(session_factory, user):
    """陈旧快照自愈（2026-10-20 拍板，模板指纹校验）：老模板生成的快照 revision 仍匹配（表单未变），
    但要素键集合与当前模板不一致——视为失配触发重算：新快照按当前五区模板全量键输出，暴露
    C 区缺口并选中追问（canSubmit=False）；重算后的新快照键集合与模板一致，再次读取幂等。"""
    async with session_factory() as db:
        async with db.begin():
            draft = await demand_service.create_draft(db, user, _draft_payload("stale-snap", {"A": {"techSubtype": "DATA_RPT"}}))
            session = await session_service.create(db, user, "SUBMIT_GUIDE", draft.id)
            did = draft.id
            # 模拟五区重构前老模板（7 要素）生成的"已齐"快照：revision 匹配但键集合残缺
            stale_reply = "要素已齐，可以提交。"
            await session_service.append(db, session.id, "ASSISTANT", stale_reply,
                {"revision": draft.revision, "canSubmit": True, "askedTarget": None, "reply": stale_reply,
                 "elements": [{"key": k, "label": k, "status": "OK", "note": ""} for k in
                              ("title", "demandTypeCode", "content", "techSubtype",
                               "businessScenario", "acceptanceCriteria", "valueImpact")],
                 "formSnapshot": {}})
    async with session_factory() as db:
        async with db.begin():
            result = await demand_service.detail(db, user, did)
    snap = json.loads(result["messages"][-1]["structuredPayload"])
    draft = await get_demand(session_factory, did)
    assert snap.get("kind") is None and snap["revision"] == draft.revision
    assert snap["reply"] != stale_reply  # 新注入的重算快照，不是回放老快照
    assert {"userRole", "userGoal", "useScenario", "painPoint"} <= {e["key"] for e in snap["elements"]}  # 五区全量键
    assert snap["canSubmit"] is False and snap["askedTarget"] is not None  # C 区缺口暴露并选中追问
    # 幂等：新快照键集合与当前模板一致，再次读取不重复注入
    async with session_factory() as db:
        async with db.begin():
            again = await demand_service.detail(db, user, did)
    assert len(again["messages"]) == len(result["messages"])


@pytest.mark.asyncio
async def test_resubmit_marks_return_notification_read(session_factory, user, admin):
    """角标闭环（2026-10-20 拍板）：打回通知在重提成功后自动已读——「我的需求」tab 角标随之下架。
    两条打回单各重提各清，未处理的仍保留提醒。"""
    async with session_factory() as db:
        async with db.begin():
            db.add(NotificationTemplate(template_code="RETURN", template_name="退回补充",
                                        title_template="退回：${demand_no}", content_template="原因：${comment}"))
    did1, _, _ = await make_submitted(session_factory, user, session=True)
    did2, _, _ = await make_submitted(session_factory, user, session=True)
    await admin_return(session_factory, admin, did1)
    await admin_return(session_factory, admin, did2)
    async with session_factory() as db:
        assert await notification_service.unread_count(db, user) == 2
    async with session_factory() as db:
        async with db.begin():
            await demand_service.submit(db, user, did1, (await db.get(Demand, did1)).revision)
    async with session_factory() as db:
        # 已重提的单通知清零；未处理的 did2 提醒仍在
        assert await notification_service.unread_count(db, user) == 1


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
async def test_light_demand_return_resubmit_follows_light_gate(session_factory, user, admin):
    """轻量需求打回后仍按 4 项最小集（2026-10-20 拍板）：口径保持 light 不升，最小集齐即放行重提。"""
    light = {"D": {"acceptanceCriteria": "首页顶部logo显示为新设计的蓝色版本"}}
    did, rev, _ = await make_submitted(session_factory, user, elements=light,
                                        ext={"mode": {"level": "light", "evidence": "换logo微调"}})
    await admin_return(session_factory, admin, did)
    demand = await get_demand(session_factory, did)
    assert demand.ext["mode"]["level"] == "light"  # 口径保持原样
    async with session_factory() as db:
        async with db.begin():
            resubmitted = await demand_service.submit(db, user, did, demand.revision)
    assert resubmitted.status == "SUBMITTED"


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
async def test_return_api_admin_gate_and_flow(client, session_factory, user, admin_headers):
    """API 层：普通用户 403，管理员 200；列表状态筛选含 NEED_INFO。"""
    did, rev, _ = await make_submitted(session_factory, user, session=True)
    user_token = (await client.post("/demandhub-api/auth/dev-login",
        json={"name": "测试用户", "wecomUserid": "test-user"})).json()["data"]["accessToken"]
    response = await client.post(f"/demandhub-api/admin/demand/{did}/return",
        json={"reason": RETURN_REASON}, headers={"Authorization": f"Bearer {user_token}"})
    # 统一响应体：BizError 走 HTTP 200 + body 业务码（403 无权限）
    assert response.json()["code"] == 403
    response = await client.post(f"/demandhub-api/admin/demand/{did}/return",
        json={"reason": RETURN_REASON}, headers=admin_headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "NEED_INFO" and data["ext"]["returnReason"]["reason"] == RETURN_REASON
    # 提报人列表「待补充」筛选可查到
    mine = (await client.get("/demandhub-api/demand/my", params={"status": "NEED_INFO"},
        headers={"Authorization": f"Bearer {user_token}"})).json()["data"]
    assert mine["total"] == 1 and mine["records"][0]["id"] == did


@pytest.mark.asyncio
async def test_need_info_count_api_lifecycle(client, session_factory, user, admin):
    """「我的需求」tab 角标口径（2026-10-20 拍板）：= 待补充需求数（NEED_INFO），与 status=NEED_INFO
    筛选同口径。打回 +1 → 重提 -1 → 撤销 -1，随业务状态自动消长，不依赖通知已读。"""
    user_token = (await client.post("/demandhub-api/auth/dev-login",
        json={"name": "测试用户", "wecomUserid": "test-user"})).json()["data"]["accessToken"]
    headers = {"Authorization": f"Bearer {user_token}"}

    async def badge() -> int:
        return (await client.get("/demandhub-api/demand/my/need-info-count", headers=headers)).json()["data"]["count"]

    did1, _, _ = await make_submitted(session_factory, user)
    did2, _, _ = await make_submitted(session_factory, user)
    assert await badge() == 0  # 已提交未打回：无角标
    await admin_return(session_factory, admin, did1)
    await admin_return(session_factory, admin, did2)
    assert await badge() == 2
    # 重提一条：角标 -1
    async with session_factory() as db:
        rev = (await db.get(Demand, did1)).revision
    response = await client.post(f"/demandhub-api/demand/{did1}/submit",
        json={"expectedRevision": rev}, headers=headers)
    assert response.json()["code"] == 0
    assert await badge() == 1
    # 撤销另一条：角标 -1
    response = await client.post(f"/demandhub-api/demand/{did2}/close",
        json={"reason": "不提了"}, headers=headers)
    assert response.json()["code"] == 0
    assert await badge() == 0
