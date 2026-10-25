"""P3 处理辅助单测：HANDLE_ASSIST 会话、提问/方案草稿、确认入 solution、废弃、LLM 降级。

覆盖口径：
- HANDLE_ASSIST 会话 get-or-create 需求级共享（同人/不同人复用同一会话）
- 生成提问 → 草稿 PENDING + ASSISTANT 消息；生成方案 → 草稿 PENDING
- 确认方案（可编辑/未编辑用原文）→ solution max+1 DRAFT「AI 生成，人工确认入库」+ 草稿 CONFIRMED
- 前置校验：非 ANALYZING 1001、QUESTIONS 类型 400、非 PENDING 1404、不存在 1403
- LLM 不可用/输出非法 → 1401 降级
"""
import json
from uuid import uuid4

from sqlalchemy import select

from app.agent.llm_client import LlmUnavailable, StreamEvent, get_llm_client
from app.core.errors import ErrorCode
from app.db.models import Solution, User

BASE = "/demandhub-api"

ACD = {"A": {"techSubtype": "DATA_RPT"},
       # B1 业务目标（2026-10-24 拍板受理侧强校验兜底）：常规科技需求受理前必填，fixture 预置
       "B": {"businessGoal": "帮部门省下专职整理岗，释放一个人力"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
             "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
       "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}


class AssistFakeArk:
    """处理辅助 LLM 桩：complete_json 返回预设输出，embed 返回固定向量。"""

    def __init__(self):
        self.next_complete: dict | str = {}
        self.embed_vector = [1.0, 0.0]
        self.complete_calls = 0
        self.unavailable = False

    def available(self):
        return True

    def on_success(self):
        pass

    async def complete_json(self, messages):
        self.complete_calls += 1
        if self.unavailable:
            raise LlmUnavailable
        raw = self.next_complete if isinstance(self.next_complete, str) else json.dumps(self.next_complete, ensure_ascii=False)
        return StreamEvent("final", raw=raw, usage={})

    async def embed(self, text):
        if self.unavailable:
            raise LlmUnavailable
        return self.embed_vector


async def make_user(factory, name, wecom_userid, role="HANDLER", type_scope=None):
    # 业务角色默认配全类型权限（贴合生产「必配」约束），按需用 type_scope 覆盖
    if type_scope is None and role in ("EXECUTIVE", "MANAGER", "HANDLER"):
        type_scope = "TECH,MATL,TRAIN"
    async with factory() as db:
        async with db.begin():
            user = User(name=name, wecom_userid=wecom_userid, channel="CHUANGJIN_LS", role=role,
                        type_scope=type_scope)
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def make_submitted(client, auth_headers) -> dict:
    resp = await client.post(BASE + "/demand", headers=auth_headers,
                             json={"clientRequestId": f"p3a-{uuid4().hex}", "title": "晨会持仓报表",
                                   "demandTypeCode": "TECH", "content": "机构业务部客户经理每天晨会前查看持仓汇总",
                                   "urgency": "NORMAL", "elements": ACD})
    draft = resp.json()["data"]
    submitted = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=auth_headers,
                                  json={"expectedRevision": draft["revision"]})
    return submitted.json()["data"]


async def to_analyzing(factory, admin, handler, demand_id):
    from app.services import triage_service
    async with factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, demand_id, None)
    async with factory() as db:
        async with db.begin():
            await triage_service.assign(db, admin, demand_id, handler.id, None)


async def assist_session(client, headers, demand_id) -> dict:
    resp = await client.post(BASE + "/agent/session", headers=headers,
                             json={"demandId": demand_id, "scene": "HANDLE_ASSIST"})
    assert resp.json()["code"] == 0, resp.text
    return resp.json()["data"]


def override_llm(client, fake):
    client._transport.app.dependency_overrides[get_llm_client] = lambda: fake


async def login(client, name, wecom_userid):
    resp = await client.post(BASE + "/auth/dev-login", json={"name": name, "wecomUserid": wecom_userid})
    return {"Authorization": "Bearer " + resp.json()["data"]["accessToken"]}


async def test_assist_session_get_or_create_shared(client, auth_headers):
    demand = await make_submitted(client, auth_headers)
    first = await assist_session(client, auth_headers, demand["id"])
    again = await assist_session(client, auth_headers, demand["id"])
    assert again["id"] == first["id"] and again["scene"] == "HANDLE_ASSIST"
    # 处理人更替/管理员接入：不同用户打开同一需求复用同一会话（需求级共享工作区）
    other = await login(client, "处理人乙", f"p3a-share-{uuid4().hex[:8]}")
    shared = await assist_session(client, other, demand["id"])
    assert shared["id"] == first["id"]


async def test_generate_questions_draft_and_message(client, auth_headers):
    demand = await make_submitted(client, auth_headers)
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.next_complete = {"questions": ["核心使用角色与频次？", "数据来源与口径确认人？", "与上下游系统的边界？"]}
    override_llm(client, fake)
    resp = await client.post(BASE + "/agent/assist/questions", headers=auth_headers,
                             json={"sessionId": session["id"]})
    assert resp.json()["code"] == 0, resp.text
    draft = resp.json()["data"]
    assert draft["status"] == "PENDING" and draft["draftType"] == "QUESTIONS"
    assert draft["content"] == ["核心使用角色与频次？", "数据来源与口径确认人？", "与上下游系统的边界？"]
    assert fake.complete_calls == 1
    # 会话追加 ASSISTANT 消息（标注 AI 生成需人工确认）
    messages = (await client.get(f"{BASE}/agent/session/{session['id']}/messages", headers=auth_headers)).json()["data"]
    assert any("【AI 生成 · 调研问题清单】（需人工确认）" in m["content"] and "· 核心使用角色与频次？" in m["content"]
               for m in messages if m["role"] == "ASSISTANT")


async def test_generate_solution_and_confirm_edited(client, auth_headers, session_factory):
    demand = await make_submitted(client, auth_headers)
    admin = await make_user(session_factory, "管理员", f"p3a-admin-{uuid4().hex[:8]}", role="ADMIN")
    handler = await make_user(session_factory, "处理人", f"p3a-handler-{uuid4().hex[:8]}")
    await to_analyzing(session_factory, admin, handler, demand["id"])
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.next_complete = {"specContent": "（AI 生成，需人工确认）需求理解", "solutionContent": "（AI 生成，需人工确认）方案内容"}
    override_llm(client, fake)
    draft = (await client.post(BASE + "/agent/assist/solution", headers=auth_headers,
                               json={"sessionId": session["id"]})).json()["data"]
    assert draft["draftType"] == "SOLUTION" and draft["status"] == "PENDING"
    # 编辑后确认入库：solution 版本 1、DRAFT、备注「AI 生成，人工确认入库」
    confirmed = (await client.post(f"{BASE}/agent/assist/drafts/{draft['id']}/confirm", headers=auth_headers,
                                   json={"specContent": "人工修订后的需求理解", "solutionContent": "人工修订后的方案",
                                         "planDeliveryAt": "2026-11-01"})).json()["data"]
    assert confirmed["status"] == "CONFIRMED" and confirmed["targetSolutionId"]
    async with session_factory() as db:
        solution = (await db.execute(select(Solution).where(Solution.id == confirmed["targetSolutionId"]))).scalar_one()
        assert solution.version == 1 and solution.status == "DRAFT"
        assert solution.spec_content == "人工修订后的需求理解"
        assert solution.solution_content == "人工修订后的方案"
        assert solution.remark == "AI 生成，人工确认入库"
        assert str(solution.plan_delivery_at) == "2026-11-01"


async def test_confirm_uses_draft_origin_when_blank(client, auth_headers, session_factory):
    demand = await make_submitted(client, auth_headers)
    admin = await make_user(session_factory, "管理员", f"p3a-admin-{uuid4().hex[:8]}", role="ADMIN")
    handler = await make_user(session_factory, "处理人", f"p3a-handler-{uuid4().hex[:8]}")
    await to_analyzing(session_factory, admin, handler, demand["id"])
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.next_complete = {"specContent": "原始需求理解", "solutionContent": "原始方案内容"}
    override_llm(client, fake)
    draft = (await client.post(BASE + "/agent/assist/solution", headers=auth_headers,
                               json={"sessionId": session["id"]})).json()["data"]
    confirmed = (await client.post(f"{BASE}/agent/assist/drafts/{draft['id']}/confirm",
                                   headers=auth_headers, json={})).json()["data"]
    async with session_factory() as db:
        solution = await db.get(Solution, confirmed["targetSolutionId"])
        assert solution.spec_content == "原始需求理解" and solution.solution_content == "原始方案内容"


async def test_confirm_rejected_when_not_analyzing(client, auth_headers):
    demand = await make_submitted(client, auth_headers)  # SUBMITTED 未受理
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.next_complete = {"specContent": "理解", "solutionContent": "方案"}
    override_llm(client, fake)
    draft = (await client.post(BASE + "/agent/assist/solution", headers=auth_headers,
                               json={"sessionId": session["id"]})).json()["data"]
    resp = await client.post(f"{BASE}/agent/assist/drafts/{draft['id']}/confirm", headers=auth_headers, json={})
    assert resp.json()["code"] == ErrorCode.ILLEGAL_STATE_TRANSITION.code


async def test_confirm_questions_type_rejected(client, auth_headers):
    demand = await make_submitted(client, auth_headers)
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.next_complete = {"questions": ["问题一？"]}
    override_llm(client, fake)
    draft = (await client.post(BASE + "/agent/assist/questions", headers=auth_headers,
                               json={"sessionId": session["id"]})).json()["data"]
    resp = await client.post(f"{BASE}/agent/assist/drafts/{draft['id']}/confirm", headers=auth_headers, json={})
    assert resp.json()["code"] == ErrorCode.PARAM_INVALID.code


async def test_discard_and_double_operate(client, auth_headers):
    demand = await make_submitted(client, auth_headers)
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.next_complete = {"questions": ["问题一？"]}
    override_llm(client, fake)
    draft = (await client.post(BASE + "/agent/assist/questions", headers=auth_headers,
                               json={"sessionId": session["id"]})).json()["data"]
    resp = await client.post(f"{BASE}/agent/assist/drafts/{draft['id']}/discard", headers=auth_headers)
    assert resp.json()["code"] == 0
    drafts = (await client.get(f"{BASE}/agent/assist/drafts", headers=auth_headers,
                               params={"demandId": demand["id"]})).json()["data"]
    assert drafts[0]["status"] == "DISCARDED"
    # 非 PENDING 重复操作 → 1404；不存在 → 1403
    again = await client.post(f"{BASE}/agent/assist/drafts/{draft['id']}/discard", headers=auth_headers)
    assert again.json()["code"] == ErrorCode.AGENT_DRAFT_CONFIRMED.code
    missing = await client.post(f"{BASE}/agent/assist/drafts/999999/discard", headers=auth_headers)
    assert missing.json()["code"] == ErrorCode.AGENT_DRAFT_NOT_FOUND.code


async def test_llm_unavailable_or_garbage_returns_1401(client, auth_headers):
    demand = await make_submitted(client, auth_headers)
    session = await assist_session(client, auth_headers, demand["id"])
    fake = AssistFakeArk()
    fake.unavailable = True
    override_llm(client, fake)
    resp = await client.post(BASE + "/agent/assist/questions", headers=auth_headers,
                             json={"sessionId": session["id"]})
    assert resp.json()["code"] == ErrorCode.AI_SERVICE_UNAVAILABLE.code
    # 输出非法 JSON 同样 1401 降级
    fake.unavailable = False
    fake.next_complete = "这不是JSON"
    resp = await client.post(BASE + "/agent/assist/solution", headers=auth_headers,
                             json={"sessionId": session["id"]})
    assert resp.json()["code"] == ErrorCode.AI_SERVICE_UNAVAILABLE.code


async def test_wrong_scene_session_rejected(client, auth_headers):
    draft = (await client.post(BASE + "/demand", headers=auth_headers,
                               json={"clientRequestId": f"p3a-{uuid4().hex}", "title": "渠道日报",
                                     "demandTypeCode": "TECH", "content": "客户经理每天需要查看渠道业务日报"})).json()["data"]
    guide = (await client.post(BASE + "/agent/session", headers=auth_headers,
                               json={"demandId": draft["id"], "scene": "SUBMIT_GUIDE"})).json()["data"]
    fake = AssistFakeArk()
    override_llm(client, fake)
    resp = await client.post(BASE + "/agent/assist/questions", headers=auth_headers,
                             json={"sessionId": guide["id"]})
    assert resp.json()["code"] == ErrorCode.PARAM_INVALID.code
