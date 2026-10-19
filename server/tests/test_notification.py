"""P4 通知中心单测（2026-10-14）。

覆盖口径（对应验收门禁「事件→通知映射全覆盖」）：
- 18 事件→7 类映射全量核对；模板 ${var} 渲染（缺失→空串、extra camel→snake、状态码原样）
- 接收人解析（蓝本 RecipientResolver）：经理/兜底管理者、提报人、处理人、被分派人、操作人剔除
- 授权范围过滤（决策③）：grant 有 type_scope 按类型过滤、无 grant 默认全类型、EXECUTIVE 直通
- 偏好：无记录=默认开、TODO 不可关、关闭后对应类不再投递
- 信箱：分页/未读数/单条已读（仅本人+幂等）/全部已读；模板 CRUD + preview（仅 ADMIN）
- 模板缺失软跳过（不炸主流程）；通知与流转同事务（流转失败不留信）
"""
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.core.errors import BizError
from app.core.statemachine import engine
from app.db.models import Demand, Notification, NotificationTemplate, User, now
from app.services import demand_service, notification_service, role_service, triage_service

ACD = {"A": {"techSubtype": "DATA_RPT"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
             "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
       "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}

# 18 事件最小模板：标题/内容带占位符用于渲染断言
TEMPLATES = {
    "SUBMIT": ("新需求：${demand_no}", "${operator_name}提交了${demand_no}「${title}」"),
    "WITHDRAW": ("已撤销：${demand_no}", "需求${demand_no}已撤销"),
    "ACCEPT": ("已受理：${demand_no}", "您提报的${demand_no}已受理"),
    "RETURN": ("退回：${demand_no}", "原因：${comment}"),
    "CLOSE": ("已关闭：${demand_no}", "原因：${comment}"),
    "ASSIGN": ("新任务：${demand_no}", "${operator_name}分派给你"),
    "CLAIM": ("已领取：${demand_no}", "您的${demand_no}已被领取"),
    "SUBMIT_REVIEW": ("待评审：${demand_no}", "${demand_no}方案待评审"),
    "REVIEW_PASS": ("评审通过：${demand_no}", "${demand_no}评审通过"),
    "REVIEW_REJECT": ("评审打回：${demand_no}", "意见：${comment}"),
    "START": ("处理中：${demand_no}", "您的${demand_no}已开始处理"),
    "SUBMIT_ACCEPTANCE": ("待验收：${demand_no}", "您的${demand_no}待验收"),
    "ACCEPT_PASS": ("验收通过：${demand_no}", "${demand_no}已归档"),
    "ACCEPT_REJECT": ("验收打回：${demand_no}", "意见：${comment}"),
    "CHANGE_TYPE": ("类型修正：${demand_no}", "${from_type}修正为${to_type}"),
    "HOLD": ("已挂起：${demand_no}", "原因：${comment}"),
    "RESUME": ("已恢复：${demand_no}", "${demand_no}已恢复"),
    "SLA_ALERT": ("SLA${level_text}：${demand_no}", "状态${to_status}停留${elapsed_minutes}分钟"),
}


# ---- 基座工具 ----

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


@pytest.fixture
async def submitter(session_factory):
    return await make_user(session_factory, "提报人", "p4n-submitter")


@pytest.fixture(autouse=True)
async def templates(session_factory):
    """每个用例前铺 18 事件模板（conftest 清库会抹掉迁移种子）。"""
    async with session_factory() as db:
        async with db.begin():
            for code, (title, content) in TEMPLATES.items():
                db.add(NotificationTemplate(
                    template_code=code, template_name=code, title_template=title,
                    content_template=content))
    return True


async def make_submitted(factory, user, type_code="TECH"):
    async with factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {
                "clientRequestId": f"p4n-{uuid4().hex}", "title": "晨会持仓报表", "demandTypeCode": type_code,
                "content": "机构业务部客户经理每天晨会前查看各机构持仓汇总", "urgency": "NORMAL",
                "elements": ACD, "fieldSources": {"demandTypeCode": "default"}})
            submitted = await demand_service.submit(db, user, demand.id, demand.revision)
            return submitted.id


async def insert_demand(factory, submitter, **overrides):
    async with factory() as db:
        async with db.begin():
            demand = Demand(
                title="夹具需求", demand_type_code="TECH", content="内容", urgency="NORMAL",
                status="SUBMITTED", submitter_id=submitter.id, submitter_name=submitter.name,
                channel="CHUANGJIN_LS", client_request_id=f"raw-{uuid4().hex}",
                create_request_hash="raw", submitted_at=now(), revision=0)
            for key, value in overrides.items():
                setattr(demand, key, value)
            db.add(demand)
            await db.flush()
            return demand.id


async def get_demand(factory, demand_id):
    async with factory() as db:
        return await db.get(Demand, demand_id)


async def mails(factory, receiver_id, template_code=None):
    async with factory() as db:
        statement = select(Notification).where(Notification.receiver_id == receiver_id)
        if template_code:
            statement = statement.where(Notification.template_code == template_code)
        return list((await db.execute(statement.order_by(Notification.id))).scalars().all())


async def mail_count(factory, receiver_id):
    async with factory() as db:
        return (await db.execute(
            select(func.count(Notification.id)).where(Notification.receiver_id == receiver_id)
        )).scalar_one()


# ---- 1. 映射与渲染 ----

def test_event_mapping_covers_blueprint_18():
    expected = {
        "TODO": {"SUBMIT", "RETURN", "REVIEW_REJECT", "ACCEPT_REJECT"},
        "STATUS_CHANGE": {"WITHDRAW", "ACCEPT", "CLOSE", "CLAIM", "REVIEW_PASS", "START",
                          "ACCEPT_PASS", "CHANGE_TYPE", "HOLD", "RESUME"},
        "ASSIGN": {"ASSIGN"}, "REVIEW_REQUEST": {"SUBMIT_REVIEW"},
        "ACCEPTANCE_REQUEST": {"SUBMIT_ACCEPTANCE"}, "SLA_ALERT": {"SLA_ALERT"},
    }
    assert len(notification_service.EVENT_NOTIFY_TYPE) == 18
    grouped = {}
    for event, notify_type in notification_service.EVENT_NOTIFY_TYPE.items():
        grouped.setdefault(notify_type, set()).add(event)
    assert grouped == expected
    assert set(notification_service.NOTIFY_TYPES) == set(expected) | {"MENTION"}
    assert notification_service.is_closable("STATUS_CHANGE")
    assert not notification_service.is_closable("TODO")


def test_render_placeholder_and_missing_var():
    assert notification_service.render("你好${name}，单据${no}", {"name": "张三", "no": "D1"}) == "你好张三，单据D1"
    assert notification_service.render("${a}${missing}${b}", {"a": "x", "b": "y"}) == "xy"
    assert notification_service.render(None, {}) == ""


@pytest.mark.asyncio
async def test_build_vars_extra_camel_to_snake(session_factory, submitter):
    did = await insert_demand(session_factory, submitter)
    async with session_factory() as db:
        demand = await db.get(Demand, did)
        variables = notification_service.build_vars(
            demand, submitter, "SUBMITTED", "TRIAGE", None,
            {"fromType": "TECH", "toType": "MATL", "assigneeId": 9})
    assert variables["from_type"] == "TECH" and variables["to_type"] == "MATL"
    assert variables["assignee_id"] == 9
    assert variables["comment"] == "" and variables["to_status"] == "TRIAGE"  # 状态码原样（决策④）


# ---- 2. 事件→接收人（服务链路 + 引擎直达） ----

@pytest.mark.asyncio
async def test_submit_notifies_manager_and_executive_fallback(session_factory, submitter):
    """SUBMIT→TODO：有经理投经理（操作人除外）；无经理兜底 EXECUTIVE。"""
    manager = await make_user(session_factory, "经理", "p4n-mgr", role="MANAGER")
    executive = await make_user(session_factory, "管理者", "p4n-exec", role="EXECUTIVE")
    did = await make_submitted(session_factory, submitter)
    found = await mails(session_factory, manager.id, "SUBMIT")
    assert len(found) == 1 and found[0].send_status == "SENT" and found[0].sent_at is not None
    assert found[0].demand_id == did and found[0].link == f"/demands/{did}"
    assert await mail_count(session_factory, executive.id) == 0  # 有经理不兜底
    assert await mail_count(session_factory, submitter.id) == 0  # 操作人剔除


@pytest.mark.asyncio
async def test_submit_fallback_executive_when_no_manager(session_factory, submitter):
    executive = await make_user(session_factory, "管理者", "p4n-exec2", role="EXECUTIVE")
    await make_submitted(session_factory, submitter)
    assert await mail_count(session_factory, executive.id) == 1


@pytest.mark.asyncio
async def test_accept_notifies_submitter(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4n-mgr2", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, manager, did, None)
    found = await mails(session_factory, submitter.id, "ACCEPT")
    assert len(found) == 1 and "已受理" in found[0].title
    # 经理本人是操作人：ACCEPT 接收人只有提报人，经理无信
    assert await mails(session_factory, manager.id, "ACCEPT") == []


@pytest.mark.asyncio
async def test_assign_and_review_events(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4n-mgr3", role="MANAGER")
    handler = await make_user(session_factory, "处理人", "p4n-hdl3")
    did = await insert_demand(session_factory, submitter, status="TRIAGE")
    async with session_factory() as db:
        async with db.begin():
            await triage_service.assign(db, manager, did, handler.id, "尽快处理")
    found = await mails(session_factory, handler.id, "ASSIGN")
    assert len(found) == 1 and "分派给你" in found[0].content

    # 评审打回 → TODO 给处理人；评审通过 → STATUS_CHANGE 给处理人
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did, "SUBMIT_REVIEW", handler)
    assert len(await mails(session_factory, manager.id, "SUBMIT_REVIEW")) == 1
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did, "REVIEW_REJECT", manager, comment="方案不完整")
    found = await mails(session_factory, handler.id, "REVIEW_REJECT")
    assert len(found) == 1 and "方案不完整" in found[0].content


@pytest.mark.asyncio
async def test_hold_resume_recipients_and_operator_excluded(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4n-mgr4", role="MANAGER")
    handler = await make_user(session_factory, "处理人", "p4n-hdl4")
    did = await insert_demand(session_factory, submitter, status="ANALYZING", assignee_id=handler.id)
    # 处理人自己挂起：接收人=提报人+处理人，剔除操作人（处理人）→ 仅提报人
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did, "HOLD", handler, comment="等数据")
    assert len(await mails(session_factory, submitter.id, "HOLD")) == 1
    assert await mails(session_factory, handler.id, "HOLD") == []
    # 经理恢复：提报人+处理人都收
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did, "RESUME", manager)
    assert len(await mails(session_factory, submitter.id, "RESUME")) == 1
    assert len(await mails(session_factory, handler.id, "RESUME")) == 1


@pytest.mark.asyncio
async def test_accept_pass_notifies_handler_and_manager(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4n-mgr5", role="MANAGER")
    handler = await make_user(session_factory, "处理人", "p4n-hdl5")
    did = await insert_demand(session_factory, submitter, status="ACCEPTANCE", assignee_id=handler.id)
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did, "ACCEPT_PASS", manager)
    assert len(await mails(session_factory, handler.id, "ACCEPT_PASS")) == 1
    assert await mails(session_factory, manager.id, "ACCEPT_PASS") == []  # 操作人剔除


@pytest.mark.asyncio
async def test_change_type_vars_and_recipients(session_factory, submitter):
    executive = await make_user(session_factory, "管理者", "p4n-exec3", role="EXECUTIVE")
    manager = await make_user(session_factory, "经理", "p4n-mgr6", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.change_type(db, executive, did, "MATL", None)
    found = await mails(session_factory, manager.id, "CHANGE_TYPE")
    assert len(found) == 1 and found[0].content == "TECH修正为MATL"


@pytest.mark.asyncio
async def test_grant_scope_filters_manager(session_factory, submitter):
    """grant 有 type_scope 按类型过滤；静态经理全类型；EXECUTIVE 直通（决策③）。"""
    scoped = await make_user(session_factory, "授权经理", "p4n-gmgr")
    static_mgr = await make_user(session_factory, "静态经理", "p4n-smgr", role="MANAGER")
    async with session_factory() as db:
        async with db.begin():
            await role_service.create_grant(
                db, user_id=scoped.id, role_code="MANAGER", org_id=None,
                demand_type_scope="TECH", effective_from=None, effective_to=None, granted_by=None)
    tech_id = await make_submitted(session_factory, submitter, "TECH")
    matl_id = await make_submitted(session_factory, submitter, "MATL")
    scoped_mails = await mails(session_factory, scoped.id, "SUBMIT")
    assert [m.demand_id for m in scoped_mails] == [tech_id]  # MATL 不在授权范围
    static_mails = await mails(session_factory, static_mgr.id, "SUBMIT")
    assert {m.demand_id for m in static_mails} == {tech_id, matl_id}  # 静态经理全类型


# ---- 3. 偏好 ----

@pytest.mark.asyncio
async def test_preference_default_on_and_todo_not_closable(session_factory, submitter):
    async with session_factory() as db:
        prefs = await notification_service.get_preferences(db, submitter)
    assert len(prefs) == 7 and all(p["enabled"] for p in prefs)
    todo = next(p for p in prefs if p["notifyType"] == "TODO")
    assert todo["closable"] is False
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await notification_service.set_preference(db, submitter, "TODO", False)
            assert error.value.code == 1000
            with pytest.raises(BizError) as error:
                await notification_service.set_preference(db, submitter, "UNKNOWN", True)
            assert error.value.code == 400


@pytest.mark.asyncio
async def test_disabled_type_not_delivered(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4n-mgr7", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    # 提报人关闭 STATUS_CHANGE：ACCEPT 不投递；RETURN（TODO）仍投递
    async with session_factory() as db:
        async with db.begin():
            await notification_service.set_preference(db, submitter, "STATUS_CHANGE", False)
            await triage_service.accept(db, manager, did, None)
    assert await mails(session_factory, submitter.id, "ACCEPT") == []
    did2 = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did2, "RETURN", manager, comment="要素不全")
    assert len(await mails(session_factory, submitter.id, "RETURN")) == 1
    # 重新打开后恢复投递
    async with session_factory() as db:
        async with db.begin():
            await notification_service.set_preference(db, submitter, "STATUS_CHANGE", True)
    async with session_factory() as db:
        prefs = await notification_service.get_preferences(db, submitter)
    assert next(p for p in prefs if p["notifyType"] == "STATUS_CHANGE")["enabled"] is True


# ---- 4. 同事务与软跳过 ----

@pytest.mark.asyncio
async def test_template_missing_soft_skip(session_factory, submitter):
    """模板被停用：流转照常，仅不写信（软跳过）。"""
    async with session_factory() as db:
        async with db.begin():
            row = (await db.execute(
                select(NotificationTemplate).where(NotificationTemplate.template_code == "ACCEPT")
            )).scalar_one()
            row.status = "INACTIVE"
    manager = await make_user(session_factory, "经理", "p4n-mgr8", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, manager, did, None)
    assert (await get_demand(session_factory, did)).status == "TRIAGE"
    assert await mails(session_factory, submitter.id, "ACCEPT") == []


@pytest.mark.asyncio
async def test_no_mail_when_transition_rolls_back(session_factory, submitter):
    """同事务口径：流转失败回滚后不留信。"""
    manager = await make_user(session_factory, "经理", "p4n-mgr9", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        with pytest.raises(BizError):  # TRIAGE 状态重复 ACCEPT → 非法流转，事务不回写
            async with db.begin():
                await triage_service.accept(db, manager, did, None)
                await triage_service.accept(db, manager, did, None)
    assert await mail_count(session_factory, submitter.id) == 0


# ---- 5. 信箱与模板 API ----

async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_api_mailbox(client, session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4n-amgr", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, manager, did, None)
    manager_headers = await _login(client, "经理", "p4n-amgr")
    submitter_headers = await _login(client, "提报人", "p4n-submitter")

    unread = await client.get("/demandhub-api/notification/mine/unread-count", headers=submitter_headers)
    assert unread.json()["data"]["count"] == 1
    page = await client.get("/demandhub-api/notification/mine", headers=submitter_headers,
                            params={"current": 1, "size": 10, "isRead": "false"})
    data = page.json()["data"]
    assert data["total"] == 1 and data["pages"] == 1 and data["records"][0]["isRead"] is False
    assert data["records"][0]["notifyType"] == "STATUS_CHANGE"
    mail_id = data["records"][0]["id"]

    # 他人信件不可代读（updated=0）；本人已读幂等
    assert (await client.put(f"/demandhub-api/notification/{mail_id}/read",
                             headers=manager_headers)).json()["data"]["updated"] == 0
    assert (await client.put(f"/demandhub-api/notification/{mail_id}/read",
                             headers=submitter_headers)).json()["data"]["updated"] == 1
    assert (await client.put(f"/demandhub-api/notification/{mail_id}/read",
                             headers=submitter_headers)).json()["data"]["updated"] == 0
    assert (await client.get("/demandhub-api/notification/mine/unread-count",
                             headers=submitter_headers)).json()["data"]["count"] == 0

    # 再来两封 → 全部已读（RETURN 仅允许 SUBMITTED 源态，另起一单退回两次）
    did2 = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await engine.transition(db, did2, "RETURN", manager, comment="补齐要素")
            await demand_service.submit(db, submitter, did2, (await db.get(Demand, did2)).revision)
            await engine.transition(db, did2, "RETURN", manager, comment="仍不齐全")
    assert (await client.get("/demandhub-api/notification/mine/unread-count",
                             headers=submitter_headers)).json()["data"]["count"] == 2
    assert (await client.put("/demandhub-api/notification/mine/read-all",
                             headers=submitter_headers)).json()["data"]["updated"] == 2


@pytest.mark.asyncio
async def test_api_preferences(client, session_factory, submitter):
    headers = await _login(client, "提报人", "p4n-submitter")
    got = await client.get("/demandhub-api/notification/preferences", headers=headers)
    assert got.json()["code"] == 0 and len(got.json()["data"]) == 7
    saved = await client.put("/demandhub-api/notification/preferences", headers=headers,
                             json={"notifyType": "STATUS_CHANGE", "enabled": False})
    assert saved.json()["code"] == 0
    got = await client.get("/demandhub-api/notification/preferences", headers=headers)
    assert next(p for p in got.json()["data"]
                if p["notifyType"] == "STATUS_CHANGE")["enabled"] is False
    closed = await client.put("/demandhub-api/notification/preferences", headers=headers,
                              json={"notifyType": "TODO", "enabled": False})
    assert closed.json()["code"] == 1000


@pytest.mark.asyncio
async def test_api_template_admin(client, session_factory, admin_headers):
    await make_user(session_factory, "处理人", "p4n-ahdl")
    user_headers = await _login(client, "处理人", "p4n-ahdl")

    assert (await client.get("/demandhub-api/admin/notification-templates",
                             headers=user_headers)).json()["code"] == 403
    listed = await client.get("/demandhub-api/admin/notification-templates", headers=admin_headers)
    assert listed.json()["code"] == 0 and len(listed.json()["data"]) == len(TEMPLATES)

    created = await client.post("/demandhub-api/admin/notification-templates", headers=admin_headers,
                                json={"templateCode": "MENTION", "templateName": "提及提醒",
                                      "titleTemplate": "${operator_name}提到了你",
                                      "contentTemplate": "在${demand_no}中提到了你"})
    assert created.json()["code"] == 0
    duplicated = await client.post("/demandhub-api/admin/notification-templates", headers=admin_headers,
                                   json={"templateCode": "MENTION", "templateName": "x",
                                         "titleTemplate": "x", "contentTemplate": "x"})
    assert duplicated.json()["code"] == 409

    template_id = created.json()["data"]["id"]
    updated = await client.put(f"/demandhub-api/admin/notification-templates/{template_id}",
                               headers=admin_headers, json={"status": "INACTIVE"})
    assert updated.json()["data"]["status"] == "INACTIVE"
    missing = await client.put("/demandhub-api/admin/notification-templates/999999",
                               headers=admin_headers, json={"status": "ACTIVE"})
    assert missing.json()["code"] == 404

    preview = await client.post("/demandhub-api/admin/notification-templates/preview",
                                headers=admin_headers,
                                json={"templateCode": "SUBMIT", "variables": {"demand_no": "D20261014001",
                                                                              "operator_name": "张三", "title": "持仓"}})
    assert preview.json()["data"]["title"] == "新需求：D20261014001"
    assert preview.json()["data"]["content"] == "张三提交了D20261014001「持仓」"
    # 入参模板覆盖库内模板
    overridden = await client.post("/demandhub-api/admin/notification-templates/preview",
                                   headers=admin_headers,
                                   json={"templateCode": "SUBMIT", "titleTemplate": "覆盖${demand_no}",
                                         "variables": {"demand_no": "D1"}})
    assert overridden.json()["data"]["title"] == "覆盖D1"

    assert (await client.delete(f"/demandhub-api/admin/notification-templates/{template_id}",
                                headers=admin_headers)).json()["code"] == 0
    assert (await client.delete(f"/demandhub-api/admin/notification-templates/{template_id}",
                                headers=admin_headers)).json()["code"] == 404
