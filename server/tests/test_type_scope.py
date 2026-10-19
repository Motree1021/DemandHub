"""需求类型权限单测（2026-10-16 拍板：按人统一配；空值=无权限；ADMIN 直通；提报人本人单不受限）。

覆盖口径：
- role_service 助手：parse_type_scope（非法码丢弃、按 TYPE_CODES 序）/ user_type_codes（ADMIN→None，空→[]）
- 列表过滤：queue/pool/counts/list_mine 按 type_scope；空 scope 恒假查不到；ADMIN 不过滤
- 动作拦截：accept/claim/change_type 越类型 1126；assign 双校验（经理本人 + 被分派处理人均须覆盖）
- 详情可见性：get_viewable 越类型按「不存在」（1002，不暴露单存在性）；提报人看本人单不受限
- 看板过滤：manager_board/org_board 只统计 scope 内类型
- assignees 接口：typeCode 必传；候选人按 scope 过滤（ADMIN 候选直通）；非经理族 403
- 用户管理联动：sync_user_roles / create / update_roles 的 types 必填、非法码 400、非业务角色清空；
  create 多角色建号（主角色+兼任授权行一次落位，含 ADMIN 强制主角色）
"""
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.errors import BizError
from app.db.models import Demand, DemandRoleGrant, User, now
from app.services import flow_service, role_service, stat_service, triage_service

BASE = "/demandhub-api"


# ---- 基座工具 ----

async def make_user(factory, name, wecom_userid, role="HANDLER", type_scope=None):
    async with factory() as db:
        async with db.begin():
            user = User(name=name, wecom_userid=wecom_userid, channel="CHUANGJIN_LS", role=role,
                        type_scope=type_scope)
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def insert_demand(factory, submitter, type_code="TECH", **overrides):
    async with factory() as db:
        async with db.begin():
            demand = Demand(
                title="类型权限需求", demand_type_code=type_code, content="内容", urgency="NORMAL",
                status="SUBMITTED", submitter_id=submitter.id, submitter_name=submitter.name,
                channel="CHUANGJIN_LS", client_request_id=f"ts-{uuid4().hex}",
                create_request_hash="raw", submitted_at=now(), revision=0)
            for key, value in overrides.items():
                setattr(demand, key, value)
            db.add(demand)
            await db.flush()
            return demand.id


@pytest.fixture
async def submitter(session_factory):
    return await make_user(session_factory, "提报人", "ts-submitter", role="REPORTER")


async def _login(client, name, wecom_userid):
    response = await client.post(BASE + "/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


# ---- 1. 助手函数 ----

def test_parse_type_scope_orders_and_drops_invalid():
    assert role_service.parse_type_scope(None) == []
    assert role_service.parse_type_scope("") == []
    assert role_service.parse_type_scope("MATL,TECH,NOPE") == ["TECH", "MATL"]  # 非法码丢弃、按 TYPE_CODES 序


def test_user_type_codes_semantics():
    admin = User(name="a", wecom_userid="ts-pure-admin", channel="ACCOUNT", role="ADMIN")
    assert role_service.user_type_codes(admin) is None  # ADMIN 直通（不过滤）
    reporter = User(name="r", wecom_userid="ts-pure-reporter", channel="ACCOUNT", role="REPORTER")
    assert role_service.user_type_codes(reporter) == []  # 空值=无权限（严格口径）
    scoped = User(name="m", wecom_userid="ts-pure-mgr", channel="ACCOUNT", role="MANAGER",
                  type_scope="TECH")
    assert role_service.user_type_codes(scoped) == ["TECH"]


# ---- 2. 列表过滤 ----

@pytest.mark.asyncio
async def test_queue_pool_counts_filtered_by_scope(session_factory, submitter):
    tech_q = await insert_demand(session_factory, submitter, "TECH")
    await insert_demand(session_factory, submitter, "MATL")
    tech_p = await insert_demand(session_factory, submitter, "TECH", status="TRIAGE")
    await insert_demand(session_factory, submitter, "TRAIN", status="TRIAGE")
    tech_mgr = await make_user(session_factory, "科技经理", "ts-mgr1", role="MANAGER", type_scope="TECH")
    empty_mgr = await make_user(session_factory, "空权经理", "ts-mgr2", role="MANAGER")  # 未配类型
    admin = await make_user(session_factory, "管理员", "ts-admin1", role="ADMIN")
    async with session_factory() as db:
        rows, total = await triage_service.list_queue(
            db, tech_mgr, urgency=None, type_code=None, page=1, size=10)
        assert total == 1 and rows[0].id == tech_q
        pool, pool_total = await triage_service.list_pool(db, tech_mgr, urgency=None, page=1, size=10)
        assert pool_total == 1 and pool[0].id == tech_p
        assert await triage_service.counts(db, tech_mgr) == {"queue": 1, "pool": 1}
        # 空 scope 恒假：队列/池/计数全看不到（拍板「空值=无权限」）
        _, empty_total = await triage_service.list_queue(
            db, empty_mgr, urgency=None, type_code=None, page=1, size=10)
        assert empty_total == 0
        assert await triage_service.counts(db, empty_mgr) == {"queue": 0, "pool": 0}
        # ADMIN 直通不过滤
        assert await triage_service.counts(db, admin) == {"queue": 2, "pool": 2}


@pytest.mark.asyncio
async def test_list_mine_filtered_by_scope(session_factory, submitter):
    handler = await make_user(session_factory, "处理人", "ts-hdl-mine", type_scope="TECH")
    tech_id = await insert_demand(session_factory, submitter, "TECH",
                                  status="ANALYZING", assignee_id=handler.id)
    await insert_demand(session_factory, submitter, "MATL", status="ANALYZING", assignee_id=handler.id)
    async with session_factory() as db:
        mine, total = await triage_service.list_mine(db, handler, status=None, page=1, size=10)
        assert total == 1 and mine[0].id == tech_id


# ---- 3. 动作拦截 ----

@pytest.mark.asyncio
async def test_accept_and_claim_denied_by_scope(session_factory, submitter):
    tech_id = await insert_demand(session_factory, submitter, "TECH")
    matl_mgr = await make_user(session_factory, "物料经理", "ts-mgr3", role="MANAGER", type_scope="MATL")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.accept(db, matl_mgr, tech_id, None)
            assert error.value.code == 1126
    triage_id = await insert_demand(session_factory, submitter, "TECH", status="TRIAGE")
    matl_handler = await make_user(session_factory, "物料处理", "ts-hdl1", type_scope="MATL")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.claim(db, matl_handler, triage_id)
            assert error.value.code == 1126
    # 覆盖该类型的处理人可正常领取（冒烟）
    tech_handler = await make_user(session_factory, "科技处理", "ts-hdl2", type_scope="TECH")
    async with session_factory() as db:
        async with db.begin():
            claimed = await triage_service.claim(db, tech_handler, triage_id)
            assert claimed.status == "ANALYZING" and claimed.assignee_id == tech_handler.id


@pytest.mark.asyncio
async def test_assign_double_check(session_factory, submitter):
    """assign 双校验：经理本人越类型 1126；被分派处理人不覆盖该类型同样 1126。"""
    triage_id = await insert_demand(session_factory, submitter, "TECH", status="TRIAGE")
    tech_mgr = await make_user(session_factory, "科技经理", "ts-mgr4", role="MANAGER", type_scope="TECH")
    matl_mgr = await make_user(session_factory, "物料经理", "ts-mgr5", role="MANAGER", type_scope="MATL")
    tech_handler = await make_user(session_factory, "科技处理", "ts-hdl3", type_scope="TECH,MATL,TRAIN")
    matl_handler = await make_user(session_factory, "物料处理", "ts-hdl4", type_scope="MATL")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.assign(db, matl_mgr, triage_id, tech_handler.id, None)
            assert error.value.code == 1126
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:
                await triage_service.assign(db, tech_mgr, triage_id, matl_handler.id, None)
            assert error.value.code == 1126
    async with session_factory() as db:
        async with db.begin():
            assigned = await triage_service.assign(db, tech_mgr, triage_id, tech_handler.id, None)
            assert assigned.status == "ANALYZING" and assigned.assignee_id == tech_handler.id


@pytest.mark.asyncio
async def test_change_type_requires_both_types_in_scope(session_factory, submitter):
    tech_id = await insert_demand(session_factory, submitter, "TECH")
    exec_tech = await make_user(session_factory, "科技管理", "ts-exec1", role="EXECUTIVE", type_scope="TECH")
    exec_tm = await make_user(session_factory, "双科管理", "ts-exec2", role="EXECUTIVE",
                              type_scope="TECH,MATL")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:  # 新类型 MATL 越权
                await triage_service.change_type(db, exec_tech, tech_id, "MATL", None)
            assert error.value.code == 1126
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:  # 新类型 TRAIN 越权
                await triage_service.change_type(db, exec_tm, tech_id, "TRAIN", None)
            assert error.value.code == 1126
            changed = await triage_service.change_type(db, exec_tm, tech_id, "MATL", None)
            assert changed.demand_type_code == "MATL"
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:  # 改完是 MATL，仅 TECH 权限者原类型越权
                await triage_service.change_type(db, exec_tech, tech_id, "TECH", None)
            assert error.value.code == 1126


@pytest.mark.asyncio
async def test_admin_bypasses_type_scope(session_factory, submitter):
    admin = await make_user(session_factory, "管理员", "ts-admin2", role="ADMIN")
    tech_id = await insert_demand(session_factory, submitter, "TECH")
    async with session_factory() as db:
        async with db.begin():
            await triage_service.accept(db, admin, tech_id, None)
            changed = await triage_service.change_type(db, admin, tech_id, "TRAIN", None)
            assert changed.demand_type_code == "TRAIN"


# ---- 4. 详情可见性 ----

@pytest.mark.asyncio
async def test_get_viewable_scoped(session_factory, submitter):
    tech_id = await insert_demand(session_factory, submitter, "TECH")
    matl_mgr = await make_user(session_factory, "物料经理", "ts-mgr6", role="MANAGER", type_scope="MATL")
    tech_mgr = await make_user(session_factory, "科技经理", "ts-mgr7", role="MANAGER", type_scope="TECH")
    async with session_factory() as db:
        with pytest.raises(BizError) as error:  # 越类型按「不存在」，不暴露单存在性
            await flow_service.get_viewable(db, matl_mgr, tech_id)
        assert error.value.code == 1002
        assert (await flow_service.get_viewable(db, tech_mgr, tech_id)).id == tech_id
        # 提报人看本人单不受类型权限限制（拍板口径）
        assert (await flow_service.get_viewable(db, submitter, tech_id)).id == tech_id


# ---- 5. 看板过滤 ----

@pytest.mark.asyncio
async def test_boards_filtered_by_scope(session_factory, submitter):
    await insert_demand(session_factory, submitter, "TECH")
    await insert_demand(session_factory, submitter, "MATL")
    tech_exec = await make_user(session_factory, "科技管理", "ts-exec3", role="EXECUTIVE", type_scope="TECH")
    admin = await make_user(session_factory, "管理员", "ts-admin3", role="ADMIN")
    async with session_factory() as db:
        data = await stat_service.manager_board(db, tech_exec, "month")
        assert data["kpi"]["monthNew"] == 1 and data["kpi"]["inflight"] == 1
        assert {row["typeCode"] for row in data["typeDistribution"]} == {"TECH"}
        org = await stat_service.org_board(db, tech_exec)
        assert org["pendingAccept"] == 1
        full = await stat_service.manager_board(db, admin, "month")
        assert full["kpi"]["monthNew"] == 2


# ---- 6. assignees 候选人过滤 ----

@pytest.mark.asyncio
async def test_assignees_api_filters_candidates(client, session_factory):
    await make_user(session_factory, "经理", "ts-mgr8", role="MANAGER", type_scope="TECH,MATL,TRAIN")
    await make_user(session_factory, "科技处理", "ts-hdl5", type_scope="TECH")
    await make_user(session_factory, "物料处理", "ts-hdl6", type_scope="MATL")
    await make_user(session_factory, "空权处理", "ts-hdl7")  # 未配类型永不入选
    await make_user(session_factory, "管理员", "ts-admin4", role="ADMIN")  # ADMIN 候选直通
    manager_headers = await _login(client, "经理", "ts-mgr8")
    resp = await client.get(BASE + "/triage/assignees", params={"typeCode": "TECH"},
                            headers=manager_headers)
    assert resp.json()["code"] == 0
    assert {row["name"] for row in resp.json()["data"]} == {"科技处理", "管理员"}
    # typeCode 必传（Query 校验失败统一 body 业务码 400）
    missing = await client.get(BASE + "/triage/assignees", headers=manager_headers)
    assert missing.json()["code"] == 400
    # 非经理族调用 403
    handler_headers = await _login(client, "科技处理", "ts-hdl5")
    denied = await client.get(BASE + "/triage/assignees", params={"typeCode": "TECH"},
                              headers=handler_headers)
    assert denied.json()["code"] == 403


# ---- 7. 用户管理联动 ----

@pytest.mark.asyncio
async def test_sync_user_roles_type_rules(session_factory):
    user = await make_user(session_factory, "多面", "ts-multi", role="REPORTER")
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:  # 业务角色缺 types
                await role_service.sync_user_roles(db, user, ["MANAGER"], granted_by=None)
            assert error.value.code == 400 and "需求类型" in error.value.message
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as error:  # 非法类型码
                await role_service.sync_user_roles(db, user, ["MANAGER"], ["NOPE"], granted_by=None)
            assert error.value.code == 400
    async with session_factory() as db:
        async with db.begin():
            await role_service.sync_user_roles(db, user, ["MANAGER"], ["MATL", "TECH"], granted_by=None)
            fresh = await db.get(User, user.id)
            assert fresh.type_scope == "TECH,MATL"  # 落库按 TYPE_CODES 序
            # 切回纯提报人 → 类型权限清空（不留垃圾数据）
            await role_service.sync_user_roles(db, fresh, ["REPORTER"], granted_by=None)
            assert (await db.get(User, user.id)).type_scope is None


@pytest.mark.asyncio
async def test_create_and_update_user_api_type_rules(client, session_factory, admin_headers):
    # 业务角色缺 types → 400
    lacking = await client.post(BASE + "/admin/users", headers=admin_headers,
                                json={"loginAccount": "tsu1", "name": "缺类型",
                                      "initialPassword": "Abcd1234", "role": "MANAGER",
                                      "phone": "13900001001"})
    assert lacking.json()["code"] == 400
    # 配上 types → 出参 typeScope 有序
    created = await client.post(BASE + "/admin/users", headers=admin_headers,
                                json={"loginAccount": "tsu1", "name": "科技经理",
                                      "initialPassword": "Abcd1234", "role": "MANAGER",
                                      "types": ["MATL", "TECH"], "phone": "13900001001"})
    assert created.json()["code"] == 0
    assert created.json()["data"]["typeScope"] == ["TECH", "MATL"]
    uid = created.json()["data"]["id"]
    # 管理员/提报人不需要 types
    admin_user = await client.post(BASE + "/admin/users", headers=admin_headers,
                                   json={"loginAccount": "tsu2", "name": "二号管理",
                                         "initialPassword": "Abcd1234", "role": "ADMIN",
                                         "phone": "13900001002"})
    assert admin_user.json()["code"] == 0 and admin_user.json()["data"]["typeScope"] is None
    # 改角色缺 types → 400；配上 → 联动更新
    bad = await client.put(f"{BASE}/admin/users/{uid}/roles", headers=admin_headers,
                           json={"roles": ["HANDLER"]})
    assert bad.json()["code"] == 400
    updated = await client.put(f"{BASE}/admin/users/{uid}/roles", headers=admin_headers,
                               json={"roles": ["HANDLER"], "types": ["TRAIN"]})
    assert updated.json()["code"] == 0 and updated.json()["data"]["typeScope"] == ["TRAIN"]
    cleared = await client.put(f"{BASE}/admin/users/{uid}/roles", headers=admin_headers,
                               json={"roles": ["REPORTER"]})
    assert cleared.json()["code"] == 0 and cleared.json()["data"]["typeScope"] is None
    # 列表带出 typeScope
    listing = await client.get(BASE + "/admin/users?keyword=tsu2", headers=admin_headers)
    assert listing.json()["data"]["list"][0]["typeScope"] is None


@pytest.mark.asyncio
async def test_create_user_multi_roles(client, session_factory, admin_headers):
    """多角色建号（2026-10-18，与改角色同口径）：主角色+兼任一次落位；兼任落空白授权行；含 ADMIN 强制主角色。"""
    # 经理 + 处理人：主角色 MANAGER（首个），HANDLER 落兼任授权行；types 有序落 type_scope
    created = await client.post(BASE + "/admin/users", headers=admin_headers,
                                json={"loginAccount": "tsm1", "name": "经理兼处理",
                                      "initialPassword": "Abcd1234", "phone": "13900002001",
                                      "roles": ["MANAGER", "HANDLER"], "types": ["MATL", "TECH"]})
    assert created.json()["code"] == 0
    data = created.json()["data"]
    assert data["role"] == "MANAGER" and data["roles"] == ["MANAGER", "HANDLER"]
    assert data["typeScope"] == ["TECH", "MATL"]
    async with session_factory() as db:
        async with db.begin():
            grants = (await db.execute(select(DemandRoleGrant).where(
                DemandRoleGrant.user_id == data["id"], DemandRoleGrant.is_deleted == 0))).scalars().all()
            assert {row.role_code for row in grants} == {"HANDLER"}
            user = (await db.execute(select(User).where(User.login_account == "tsm1"))).scalar_one()
            assert await role_service.effective_roles(db, user) == frozenset({"MANAGER", "HANDLER"})
    # 含 ADMIN：强制主角色 ADMIN；有效角色仍含业务角色 → types 必填
    lacking = await client.post(BASE + "/admin/users", headers=admin_headers,
                                json={"loginAccount": "tsm2", "name": "管理兼经理",
                                      "initialPassword": "Abcd1234", "phone": "13900002002",
                                      "roles": ["MANAGER", "ADMIN"]})
    assert lacking.json()["code"] == 400
    admin_user = await client.post(BASE + "/admin/users", headers=admin_headers,
                                   json={"loginAccount": "tsm2", "name": "管理兼经理",
                                         "initialPassword": "Abcd1234", "phone": "13900002002",
                                         "roles": ["MANAGER", "ADMIN"], "types": ["TECH"]})
    assert admin_user.json()["code"] == 0
    data2 = admin_user.json()["data"]
    assert data2["role"] == "ADMIN" and data2["roles"] == ["ADMIN", "MANAGER"]
    assert data2["typeScope"] == ["TECH"]
