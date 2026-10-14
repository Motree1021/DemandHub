"""P4 角色扩展单测（2026-10-14）。

覆盖口径：
- 有效角色解析：静态 role ∪ 生效授权；过期/未生效/已回收授权不计
- 授权管理：新增/查重/修改/回收（is_deleted=行 id 可反复授权）、非法参数与 1121/1122
- 状态机角色映射（蓝本口径）：MANAGER 受理族、EXECUTIVE 改型、HANDLER+MANAGER 可代办族、ADMIN 直通
- 授权升权：HANDLER + MANAGER 授权可执行受理；require_role 守卫 grant 感知（API 级）
"""
from datetime import timedelta
from uuid import uuid4

import pytest

from app.core.errors import BizError
from app.db.models import Demand, User, now
from app.services import role_service, triage_service

ACD = {"A": {"techSubtype": "DATA_RPT"},
       "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各机构持仓汇总",
             "useScenario": "客户经理每天晨会前查看各机构持仓", "painPoint": "手工汇总20多个机构持仓每次近1小时"},
       "D": {"functionDescription": "按机构汇总前一交易日持仓并展示", "inputOutput": "输入交易流水输出持仓汇总报表",
             "acceptanceCriteria": "连续7天与核心系统对账误差为0"}}


# ---- 基座工具 ----

async def make_user(factory, name, wecom_userid, role="HANDLER"):
    async with factory() as db:
        async with db.begin():
            user = User(name=name, wecom_userid=wecom_userid, channel="CHUANGJIN_LS", role=role)
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def make_submitted(factory, user):
    from app.services import demand_service

    async with factory() as db:
        async with db.begin():
            demand = await demand_service.create_draft(db, user, {
                "clientRequestId": f"p4-{uuid4().hex}", "title": "晨会持仓报表", "demandTypeCode": "TECH",
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


@pytest.fixture
async def submitter(session_factory):
    return await make_user(session_factory, "提报人", "p4-submitter")


# ---- 1. 有效角色解析 ----

@pytest.mark.asyncio
async def test_effective_roles_union_and_expiry(session_factory):
    user = await make_user(session_factory, "小权", "p4-u1")
    async with session_factory() as db:
        assert await role_service.effective_roles(db, user) == frozenset({"HANDLER"})

    async with session_factory() as db:
        async with db.begin():
            manager_grant = await role_service.create_grant(
                db, user_id=user.id, role_code="MANAGER", org_id=None,
                demand_type_scope=None, effective_from=None, effective_to=None, granted_by=None)
            # 已过期 / 未生效 / 不计入
            await role_service.create_grant(
                db, user_id=user.id, role_code="EXECUTIVE", org_id=None,
                demand_type_scope=None, effective_from=None,
                effective_to=now() - timedelta(days=1), granted_by=None)
            await role_service.create_grant(
                db, user_id=user.id, role_code="ADMIN", org_id=None,
                demand_type_scope=None, effective_from=now() + timedelta(days=1),
                effective_to=None, granted_by=None)
        assert await role_service.effective_roles(db, user) == frozenset({"HANDLER", "MANAGER"})
        await role_service.delete_grant(db, manager_grant.id)
        assert await role_service.effective_roles(db, user) == frozenset({"HANDLER"})


# ---- 2. 授权管理 ----

@pytest.mark.asyncio
async def test_grant_crud_and_recreate_after_delete(session_factory):
    user = await make_user(session_factory, "小权", "p4-u2")
    other = await make_user(session_factory, "小它", "p4-u3")
    async with session_factory() as db:
        async with db.begin():
            grant = await role_service.create_grant(
                db, user_id=user.id, role_code="MANAGER", org_id=None,
                demand_type_scope="TECH", effective_from=None, effective_to=None, granted_by=None)
            assert grant.id is not None
            # 同人同角色同范围查重（1122）
            with pytest.raises(BizError) as error:
                await role_service.create_grant(
                    db, user_id=user.id, role_code="MANAGER", org_id=None,
                    demand_type_scope="TECH", effective_from=None, effective_to=None, granted_by=None)
            assert error.value.code == 1122
            # 不同范围可共存
            await role_service.create_grant(
                db, user_id=user.id, role_code="MANAGER", org_id=None,
                demand_type_scope="MATL", effective_from=None, effective_to=None, granted_by=None)
            # 修改（排除自身查重）；与他人已有授权撞范围仍 1122
            updated = await role_service.update_grant(
                db, grant.id, user_id=user.id, role_code="MANAGER", org_id=None,
                demand_type_scope="TECH,TRAIN", effective_from=None, effective_to=None)
            assert updated.demand_type_scope == "TECH,TRAIN"
            await role_service.create_grant(
                db, user_id=other.id, role_code="EXECUTIVE", org_id=None,
                demand_type_scope=None, effective_from=None, effective_to=None, granted_by=None)
            with pytest.raises(BizError) as error:
                await role_service.update_grant(
                    db, grant.id, user_id=other.id, role_code="EXECUTIVE", org_id=None,
                    demand_type_scope=None, effective_from=None, effective_to=None)
            assert error.value.code == 1122

            rows, total = await role_service.page_grants(
                db, user_id=user.id, role_code=None, page=1, size=20)
            assert total == 2
            # 回收：is_deleted 置行 id；分页不再可见；同元组可再次授权
            await role_service.delete_grant(db, grant.id)
            rows, total = await role_service.page_grants(
                db, user_id=user.id, role_code=None, page=1, size=20)
            assert total == 1
            recreated = await role_service.create_grant(
                db, user_id=user.id, role_code="MANAGER", org_id=None,
                demand_type_scope="TECH,TRAIN", effective_from=None, effective_to=None, granted_by=None)
            assert recreated.id != grant.id
            # 重复回收 → 1121
            with pytest.raises(BizError) as error:
                await role_service.delete_grant(db, grant.id)
            assert error.value.code == 1121


@pytest.mark.asyncio
async def test_grant_param_validation(session_factory):
    user = await make_user(session_factory, "小权", "p4-u4")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await role_service.create_grant(
                    db, user_id=user.id, role_code="SUPERUSER", org_id=None,
                    demand_type_scope=None, effective_from=None, effective_to=None, granted_by=None)
            assert error.value.code == 400
            with pytest.raises(BizError) as error:
                await role_service.create_grant(
                    db, user_id=user.id, role_code="MANAGER", org_id=None,
                    demand_type_scope=None, effective_from=now() + timedelta(days=2),
                    effective_to=now() + timedelta(days=1), granted_by=None)
            assert error.value.code == 400
            with pytest.raises(BizError) as error:
                await role_service.create_grant(
                    db, user_id=999999, role_code="MANAGER", org_id=None,
                    demand_type_scope=None, effective_from=None, effective_to=None, granted_by=None)
            assert error.value.code == 1119
            with pytest.raises(BizError) as error:
                await role_service.update_grant(
                    db, 999999, user_id=user.id, role_code="MANAGER", org_id=None,
                    demand_type_scope=None, effective_from=None, effective_to=None)
            assert error.value.code == 1121


# ---- 3. 状态机角色映射（蓝本口径） ----

@pytest.mark.asyncio
async def test_manager_accept_and_assign(session_factory, submitter):
    manager = await make_user(session_factory, "经理", "p4-mgr", role="MANAGER")
    handler = await make_user(session_factory, "处理人", "p4-hdl")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, manager, did, None)
    assert (await get_demand(session_factory, did)).status == "TRIAGE"
    async with session_factory() as db:
        async with db.begin():
            await triage_service.assign(db, manager, did, handler.id, None)
    demand = await get_demand(session_factory, did)
    assert demand.status == "ANALYZING" and demand.assignee_id == handler.id


@pytest.mark.asyncio
async def test_executive_cannot_accept(session_factory, submitter):
    executive = await make_user(session_factory, "管理者", "p4-exec", role="EXECUTIVE")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.accept(db, executive, did, None)
            assert error.value.code == 403


@pytest.mark.asyncio
async def test_handler_cannot_accept(session_factory, submitter):
    handler = await make_user(session_factory, "处理人", "p4-hdl2")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.accept(db, handler, did, None)
            assert error.value.code == 403


@pytest.mark.asyncio
async def test_executive_change_type_only(session_factory, submitter):
    executive = await make_user(session_factory, "管理者", "p4-exec2", role="EXECUTIVE")
    manager = await make_user(session_factory, "经理", "p4-mgr2", role="MANAGER")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.change_type(db, manager, did, "MATL", None)
            assert error.value.code == 403
    async with session_factory() as db:
        async with db.begin():
            await triage_service.change_type(db, executive, did, "MATL", None)
    demand = await get_demand(session_factory, did)
    assert demand.demand_type_code == "MATL" and demand.status == "SUBMITTED"


@pytest.mark.asyncio
async def test_admin_still_bypasses(session_factory, submitter):
    admin = await make_user(session_factory, "管理员", "p4-admin", role="ADMIN")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, did, None)
            await triage_service.change_type(db, admin, did, "MATL", None)
    demand = await get_demand(session_factory, did)
    assert demand.status == "TRIAGE" and demand.demand_type_code == "MATL"


# ---- 4. 授权升权（grant 校验） ----

@pytest.mark.asyncio
async def test_grant_elevates_handler_to_manager(session_factory, submitter):
    """静态 HANDLER + 生效 MANAGER 授权：可受理；回收授权后即 403。"""
    user = await make_user(session_factory, "小权", "p4-u5")
    did = await make_submitted(session_factory, submitter)
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.accept(db, user, did, None)
            assert error.value.code == 403
            await role_service.create_grant(
                db, user_id=user.id, role_code="MANAGER", org_id=None,
                demand_type_scope=None, effective_from=None, effective_to=None, granted_by=None)
            await triage_service.accept(db, user, did, None)
    assert (await get_demand(session_factory, did)).status == "TRIAGE"


@pytest.mark.asyncio
async def test_manager_delegate_hold_resume(session_factory, submitter):
    """经理代办（蓝本 HANDLER_OR_MANAGER 口径）：非处理人经理可挂起/恢复。"""
    from app.services import flow_service

    manager = await make_user(session_factory, "经理", "p4-mgr3", role="MANAGER")
    handler = await make_user(session_factory, "处理人", "p4-hdl3")
    did = await insert_demand(session_factory, submitter, status="ANALYZING", assignee_id=handler.id)
    async with session_factory() as db:
        async with db.begin():
            await flow_service.hold(db, manager, did, "经理代办挂起")
    demand = await get_demand(session_factory, did)
    assert demand.hold_snapshot_status == "ANALYZING"
    async with session_factory() as db:
        async with db.begin():
            await flow_service.resume(db, manager, did)
    demand = await get_demand(session_factory, did)
    assert demand.hold_snapshot_status is None and demand.status == "ANALYZING"


# ---- 5. API 级守卫（require_role grant 感知） ----

async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_api_role_guards(client, session_factory, submitter):
    await make_user(session_factory, "经理", "p4-api-mgr", role="MANAGER")
    await make_user(session_factory, "管理者", "p4-api-exec", role="EXECUTIVE")
    await make_user(session_factory, "处理人", "p4-api-hdl")
    did = await make_submitted(session_factory, submitter)

    manager_headers = await _login(client, "经理", "p4-api-mgr")
    executive_headers = await _login(client, "管理者", "p4-api-exec")
    handler_headers = await _login(client, "处理人", "p4-api-hdl")

    # 队列查看：MANAGER/EXECUTIVE 放行，HANDLER 拒绝（BizError 走 HTTP 200 + body 业务码；
    # 成功断言一律查 body code==0，防止 HTTP 200 包裹的 500 漏网）
    assert (await client.get("/demandhub-api/triage/queue", headers=manager_headers)).json()["code"] == 0
    assert (await client.get("/demandhub-api/triage/queue", headers=executive_headers)).json()["code"] == 0
    assert (await client.get("/demandhub-api/triage/queue", headers=handler_headers)).json()["code"] == 403
    # 受理：MANAGER 放行，HANDLER 拒绝
    assert (await client.post(f"/demandhub-api/triage/{did}/accept",
                              headers=handler_headers, json={})).json()["code"] == 403
    assert (await client.post(f"/demandhub-api/triage/{did}/accept",
                              headers=manager_headers, json={})).json()["code"] == 0
    # 改型：EXECUTIVE 放行，MANAGER 拒绝
    assert (await client.post(f"/demandhub-api/triage/{did}/change-type",
                              headers=manager_headers, json={"newTypeCode": "MATL"})).json()["code"] == 403
    assert (await client.post(f"/demandhub-api/triage/{did}/change-type",
                              headers=executive_headers, json={"newTypeCode": "MATL"})).json()["code"] == 0


@pytest.mark.asyncio
async def test_api_grant_admin_crud_and_elevation(client, session_factory, submitter):
    """授权管理 API（仅 ADMIN）；API 级授权升权：HANDLER + MANAGER 授权可调受理接口。"""
    await make_user(session_factory, "小权", "p4-api-u6")
    did = await make_submitted(session_factory, submitter)
    admin_headers = await _login(client, "超管", "mvp-admin")  # 企微白名单 ADMIN（过渡期）
    user_headers = await _login(client, "小权", "p4-api-u6")

    # 非 ADMIN 访问授权管理 → 403（body 业务码）
    assert (await client.get("/demandhub-api/admin/grants", headers=user_headers)).json()["code"] == 403
    # 查用户 id（小权无授权时受理 → 403）
    assert (await client.post(f"/demandhub-api/triage/{did}/accept",
                              headers=user_headers, json={})).json()["code"] == 403
    me = await client.get("/demandhub-api/auth/me", headers=user_headers)
    uid = me.json()["data"]["id"]

    created = await client.post("/demandhub-api/admin/grants", headers=admin_headers,
                                json={"userId": uid, "roleCode": "MANAGER"})
    assert created.json()["code"] == 0, created.json()
    grant_id = created.json()["data"]["id"]
    # 重复授权同元组 → 1122
    duplicated = await client.post("/demandhub-api/admin/grants", headers=admin_headers,
                                   json={"userId": uid, "roleCode": "MANAGER"})
    assert duplicated.json()["code"] == 1122
    # 授权即时生效（无需重新登录）
    assert (await client.post(f"/demandhub-api/triage/{did}/accept",
                              headers=user_headers, json={})).json()["code"] == 0
    # 分页/回收
    page = await client.get("/demandhub-api/admin/grants", headers=admin_headers,
                            params={"userId": uid})
    assert page.json()["data"]["total"] == 1
    assert (await client.delete(f"/demandhub-api/admin/grants/{grant_id}",
                                headers=admin_headers)).json()["code"] == 0
    assert (await client.delete(f"/demandhub-api/admin/grants/{grant_id}",
                                headers=admin_headers)).json()["code"] == 1121


@pytest.mark.asyncio
async def test_api_update_user_role(client, session_factory):
    """ADMIN 调整静态角色：调整后即时生效（逐请求读库）。"""
    await make_user(session_factory, "小调", "p4-api-u7")
    admin_headers = await _login(client, "超管", "mvp-admin")
    user_headers = await _login(client, "小调", "p4-api-u7")
    me = await client.get("/demandhub-api/auth/me", headers=user_headers)
    uid = me.json()["data"]["id"]

    assert (await client.get("/demandhub-api/triage/queue", headers=user_headers)).json()["code"] == 403
    updated = await client.put(f"/demandhub-api/admin/users/{uid}/role",
                               headers=admin_headers, json={"role": "EXECUTIVE"})
    assert updated.json()["code"] == 0 and updated.json()["data"]["role"] == "EXECUTIVE"
    assert (await client.get("/demandhub-api/triage/queue", headers=user_headers)).json()["code"] == 0
    # 非法角色值 → 400（Literal 校验失败，统一响应体 body 业务码）
    invalid = await client.put(f"/demandhub-api/admin/users/{uid}/role",
                               headers=admin_headers, json={"role": "SUPERUSER"})
    assert invalid.json()["code"] == 400
