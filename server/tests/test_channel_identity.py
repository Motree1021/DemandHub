"""渠道身份（OneID）API 测试。

覆盖口径：
- SSO 建档：新渠道用户建临时人 + 渠道身份行；存量用户（人表已有、无身份行）登录补建身份行
- 未归属搜索：只列归属临时人的身份；已挂 PC 用户的不出现；keyword 过滤
- 挂接 LINK：身份改指 PC 用户、业务数据全量过户零残留、临时人停用/授权作废/票据吊销、审计落库
- OneID 生效：挂接后渠道免登进 PC 用户（角色以 PC 为准，姓名/部门不再被渠道快照覆盖）
- 改挂 REBIND：只移钥匙不搬历史数据
- 并发与校验：并发抢挂一成一 1128、挂接到非 PC 用户 400、重复挂接 1128、改挂未挂接身份 400
- 二期（2026-10-18）：待归一附同名线索 suspects（仅完全同名、仅 ACTIVE 正式用户）；
  挂接记录分页出参（LINK 带过户明细、REBIND 无）
"""
import asyncio
import json
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.core.security import hash_password
from app.db.models import (
    ChannelIdentity,
    Comment,
    Demand,
    DemandRoleGrant,
    EffortLog,
    IdentityLinkLog,
    Notification,
    NotificationPreference,
    RefreshToken,
    User,
    now,
)

BASE = "/demandhub-api"


# ---- 基座工具 ----

async def make_pc_user(factory, name, account, role="HANDLER"):
    async with factory() as db:
        async with db.begin():
            user = User(name=name, wecom_userid=f"acct:{account}", channel="ACCOUNT", role=role,
                        login_account=account, password_hash=hash_password("Passw0rd!"),
                        must_change_pwd=False)
            db.add(user)
            await db.flush()
            db.expunge(user)
            return user


async def admin_headers(client, factory, account="boss"):
    await make_pc_user(factory, "管理员", account, role="ADMIN")
    resp = await client.post(BASE + "/auth/login",
                             json={"loginAccount": account, "password": "Passw0rd!"})
    assert resp.json()["code"] == 0
    return {"Authorization": "Bearer " + resp.json()["data"]["accessToken"]}


async def channel_login(client, name, channel_user_id):
    """渠道免登（dev-login 链路）：返回响应 data（accessToken/user）。"""
    resp = await client.post(BASE + "/auth/dev-login",
                             json={"name": name, "wecomUserid": channel_user_id})
    assert resp.json()["code"] == 0
    return resp.json()["data"]


def _demand(submitter_id, title="过户单"):
    return Demand(client_request_id=uuid4().hex, create_request_hash=uuid4().hex,
                  submitter_id=submitter_id, title=title, demand_type_code="TECH",
                  status="SUBMITTED")


async def _identity_id(factory, channel_user_id):
    async with factory() as db:
        return (await db.execute(select(ChannelIdentity.id).where(
            ChannelIdentity.channel_user_id == channel_user_id))).scalar_one()


# ---- SSO 建档与存量回填 ----

async def test_sso_first_login_creates_temp_user_and_identity(client, session_factory):
    await channel_login(client, "渠道张三", "ch-new-1")
    async with session_factory() as db:
        user = (await db.execute(select(User).where(User.wecom_userid == "ch-new-1"))).scalar_one()
        assert user.channel == "CHUANGJIN_LS"  # 未归一前是渠道临时人，照常可用
        identity = (await db.execute(select(ChannelIdentity).where(
            ChannelIdentity.channel_user_id == "ch-new-1"))).scalar_one()
        assert identity.user_id == user.id
        assert identity.channel_user_name == "渠道张三"


async def test_existing_user_without_identity_backfills_on_login(client, session_factory):
    """存量用户（一期上线前已建档、无身份行）登录时补建身份行，不新建用户。"""
    async with session_factory() as db:
        async with db.begin():
            legacy = User(name="存量李四", wecom_userid="ch-old-1", channel="CHUANGJIN_LS",
                          status="ACTIVE")
            db.add(legacy)
            await db.flush()
            legacy_id = legacy.id
    await channel_login(client, "存量李四", "ch-old-1")
    async with session_factory() as db:
        users = (await db.execute(select(User).where(User.wecom_userid == "ch-old-1"))).scalars().all()
        assert len(users) == 1
        identity = (await db.execute(select(ChannelIdentity).where(
            ChannelIdentity.channel_user_id == "ch-old-1"))).scalar_one()
        assert identity.user_id == legacy_id


# ---- 未归属搜索 ----

async def test_unlinked_search_excludes_linked_and_filters_keyword(client, session_factory):
    headers = await admin_headers(client, session_factory, account="boss-search")
    await channel_login(client, "待归甲", "ch-search-a")
    await channel_login(client, "待归乙", "ch-search-b")
    await channel_login(client, "已归丙", "ch-search-c")
    pc = await make_pc_user(session_factory, "正式丙", "pc-search")
    identity_c = await _identity_id(session_factory, "ch-search-c")
    linked = await client.post(f"{BASE}/admin/users/{pc.id}/channel-identities",
                               json={"identityId": identity_c}, headers=headers)
    assert linked.json()["code"] == 0

    resp = await client.get(BASE + "/admin/channel-identities",
                            params={"linked": "false"}, headers=headers)
    assert resp.json()["code"] == 0
    ids = {i["channelUserId"] for i in resp.json()["data"]["list"]}
    assert ids == {"ch-search-a", "ch-search-b"}  # 已挂接的不在待归一

    filtered = await client.get(BASE + "/admin/channel-identities",
                                params={"linked": "false", "keyword": "待归甲"}, headers=headers)
    assert [i["channelUserId"] for i in filtered.json()["data"]["list"]] == ["ch-search-a"]

    linked_list = await client.get(BASE + "/admin/channel-identities",
                                   params={"linked": "true"}, headers=headers)
    owners = {i["channelUserId"]: i["ownerName"] for i in linked_list.json()["data"]["list"]}
    assert owners == {"ch-search-c": "正式丙"}


# ---- 挂接 LINK ----

async def test_link_transfers_data_disables_temp_and_audits(client, session_factory):
    """挂接：身份改指 PC 用户 + 业务数据过户零残留 + 临时人停用 + 授权作废 +
    票据吊销 + 偏好撞键以 PC 为准 + 审计落库（含过户明细）。"""
    headers = await admin_headers(client, session_factory, account="boss-link")
    data = await channel_login(client, "渠道临时人", "ch-link-1")
    temp_id = data["user"]["id"]
    pc = await make_pc_user(session_factory, "正式用户", "pc-link")
    async with session_factory() as db:
        async with db.begin():
            demand = _demand(temp_id)
            db.add(demand)
            await db.flush()
            demand_id = demand.id
            db.add(Comment(demand_id=demand_id, author_id=temp_id, content="渠道留言"))
            db.add(EffortLog(demand_id=demand_id, user_id=temp_id, hours=1.5,
                             work_date=date(2026, 10, 18)))
            db.add(Notification(receiver_id=temp_id, title="给临时人"))
            db.add(NotificationPreference(user_id=temp_id, notify_type="TODO_REMIND", enabled=True))
            # PC 用户已有同类型偏好：挂接后以其为准，临时人的撞键行删除
            db.add(NotificationPreference(user_id=pc.id, notify_type="TODO_REMIND", enabled=False))
            db.add(DemandRoleGrant(user_id=temp_id, role_code="MANAGER", granted_by=temp_id))
            db.add(RefreshToken(user_id=temp_id, token_hash=uuid4().hex,
                                expires_at=now() + timedelta(days=7)))
    identity_id = await _identity_id(session_factory, "ch-link-1")

    resp = await client.post(f"{BASE}/admin/users/{pc.id}/channel-identities",
                             json={"identityId": identity_id}, headers=headers)
    assert resp.json()["code"] == 0
    moved = resp.json()["data"]["movedCounts"]
    assert moved["提报需求"] == 1 and moved["评论"] == 1 and moved["工时"] == 1
    assert moved["通知"] == 1 and moved["授权操作记录"] == 1

    async with session_factory() as db:
        identity = await db.get(ChannelIdentity, identity_id)
        assert identity.user_id == pc.id
        assert (await db.get(Demand, demand_id)).submitter_id == pc.id
        # 过户零残留
        for model, column in [(Comment, "author_id"), (EffortLog, "user_id"),
                              (Notification, "receiver_id")]:
            left = (await db.execute(select(func.count()).select_from(model)
                                     .where(getattr(model, column) == temp_id))).scalar_one()
            assert left == 0
        # 临时人停用
        assert (await db.get(User, temp_id)).status == "DISABLED"
        # 偏好：撞键行删临时人的，留 PC 用户的（enabled=False 以 PC 为准）
        prefs = (await db.execute(select(NotificationPreference).where(
            NotificationPreference.notify_type == "TODO_REMIND"))).scalars().all()
        assert len(prefs) == 1 and prefs[0].user_id == pc.id and prefs[0].enabled is False
        # 临时人角色授权作废
        grants = (await db.execute(select(func.count()).select_from(DemandRoleGrant)
                                   .where(DemandRoleGrant.user_id == temp_id))).scalar_one()
        assert grants == 0
        # 票据吊销
        tokens = (await db.execute(select(func.count()).select_from(RefreshToken)
                                   .where(RefreshToken.user_id == temp_id))).scalar_one()
        assert tokens == 0
        # 审计落库
        log = (await db.execute(select(IdentityLinkLog))).scalar_one()
        assert log.action == "LINK"
        assert log.from_user_id == temp_id and log.to_user_id == pc.id
        assert log.from_user_name == "渠道临时人" and log.to_user_name == "正式用户"
        assert log.operator_name == "管理员"
        assert json.loads(log.moved_counts)["提报需求"] == 1


async def test_after_link_channel_login_enters_pc_user(client, session_factory):
    """OneID 生效：挂接后渠道免登进入 PC 用户——角色/姓名以 PC 为准，
    渠道快照只更新身份行的 channel_user_name，不再覆盖人表。"""
    headers = await admin_headers(client, session_factory, account="boss-oneid")
    await channel_login(client, "渠道名", "ch-oneid-1")
    pc = await make_pc_user(session_factory, "正式名", "pc-oneid", role="MANAGER")
    identity_id = await _identity_id(session_factory, "ch-oneid-1")
    linked = await client.post(f"{BASE}/admin/users/{pc.id}/channel-identities",
                               json={"identityId": identity_id}, headers=headers)
    assert linked.json()["code"] == 0

    data = await channel_login(client, "渠道改名", "ch-oneid-1")
    assert data["user"]["id"] == pc.id
    assert data["user"]["name"] == "正式名"  # PC 端维护为准
    assert data["user"]["role"] == "MANAGER"
    async with session_factory() as db:
        identity = await db.get(ChannelIdentity, identity_id)
        assert identity.channel_user_name == "渠道改名"  # 快照始终更新


# ---- 改挂 REBIND ----

async def test_rebind_moves_key_without_data(client, session_factory):
    """改挂：钥匙从 A 移到 B，历史数据不搬（已过户给 A 的无法再区分）；审计无明细。"""
    headers = await admin_headers(client, session_factory, account="boss-rebind")
    data = await channel_login(client, "改挂用户", "ch-rebind-1")
    temp_id = data["user"]["id"]
    pc_a = await make_pc_user(session_factory, "甲用户", "pc-rebind-a")
    pc_b = await make_pc_user(session_factory, "乙用户", "pc-rebind-b")
    async with session_factory() as db:
        async with db.begin():
            demand = _demand(temp_id, title="已过户单")
            db.add(demand)
            await db.flush()
            demand_id = demand.id
    identity_id = await _identity_id(session_factory, "ch-rebind-1")
    linked = await client.post(f"{BASE}/admin/users/{pc_a.id}/channel-identities",
                               json={"identityId": identity_id}, headers=headers)
    assert linked.json()["code"] == 0

    rebound = await client.post(f"{BASE}/admin/channel-identities/{identity_id}/rebind",
                                json={"userId": pc_b.id}, headers=headers)
    assert rebound.json()["code"] == 0
    async with session_factory() as db:
        identity = await db.get(ChannelIdentity, identity_id)
        assert identity.user_id == pc_b.id  # 钥匙移交给 B
        assert (await db.get(Demand, demand_id)).submitter_id == pc_a.id  # 历史数据留在 A
        rebind_log = (await db.execute(select(IdentityLinkLog)
                                       .where(IdentityLinkLog.action == "REBIND"))).scalar_one()
        assert rebind_log.moved_counts is None
        assert rebind_log.from_user_id == pc_a.id and rebind_log.to_user_id == pc_b.id


# ---- 校验与并发 ----

async def test_link_and_rebind_validation_guards(client, session_factory):
    headers = await admin_headers(client, session_factory, account="boss-guard")
    data = await channel_login(client, "校验用户", "ch-guard-1")
    temp_id = data["user"]["id"]
    pc = await make_pc_user(session_factory, "校验正式", "pc-guard")
    identity_id = await _identity_id(session_factory, "ch-guard-1")

    # 挂接到渠道临时人（非 PC 用户）→ 400
    to_temp = await client.post(f"{BASE}/admin/users/{temp_id}/channel-identities",
                                json={"identityId": identity_id}, headers=headers)
    assert to_temp.json()["code"] == 400
    # 身份不存在 → 1127
    missing = await client.post(f"{BASE}/admin/users/{pc.id}/channel-identities",
                                json={"identityId": 999999}, headers=headers)
    assert missing.json()["code"] == 1127
    # 改挂未挂接身份 → 400
    rebind_early = await client.post(f"{BASE}/admin/channel-identities/{identity_id}/rebind",
                                     json={"userId": pc.id}, headers=headers)
    assert rebind_early.json()["code"] == 400
    # 正常挂接后重复挂接 → 1128
    linked = await client.post(f"{BASE}/admin/users/{pc.id}/channel-identities",
                               json={"identityId": identity_id}, headers=headers)
    assert linked.json()["code"] == 0
    again = await client.post(f"{BASE}/admin/users/{pc.id}/channel-identities",
                              json={"identityId": identity_id}, headers=headers)
    assert again.json()["code"] == 1128


async def test_concurrent_link_one_wins_the_other_gets_1128(client, session_factory):
    headers = await admin_headers(client, session_factory, account="boss-race")
    await channel_login(client, "并发用户", "ch-race-1")
    pc_a = await make_pc_user(session_factory, "并发甲", "pc-race-a")
    pc_b = await make_pc_user(session_factory, "并发乙", "pc-race-b")
    identity_id = await _identity_id(session_factory, "ch-race-1")

    r1, r2 = await asyncio.gather(
        client.post(f"{BASE}/admin/users/{pc_a.id}/channel-identities",
                    json={"identityId": identity_id}, headers=headers),
        client.post(f"{BASE}/admin/users/{pc_b.id}/channel-identities",
                    json={"identityId": identity_id}, headers=headers))
    codes = sorted([r1.json()["code"], r2.json()["code"]])
    assert codes == [0, 1128]  # 行锁串行化：先到者得，后来者核对归属时发现已被抢
    async with session_factory() as db:
        identity = await db.get(ChannelIdentity, identity_id)
        assert identity.user_id in {pc_a.id, pc_b.id}
        owner = await db.get(User, identity.user_id)
        assert owner.channel == "ACCOUNT"
        # 仅一笔 LINK 审计
        logs = (await db.execute(select(IdentityLinkLog))).scalars().all()
        assert len(logs) == 1 and logs[0].to_user_id == identity.user_id


async def test_users_list_channel_filter_excludes_channel_temp_users(client, session_factory):
    """用户管理只管网内正式用户：channel=ACCOUNT 过滤后渠道临时人不出现；
    不传 channel 保持原行为（全量），渠道临时人的可见性由「渠道身份」页承载。"""
    headers = await admin_headers(client, session_factory, account="boss-filter")
    await channel_login(client, "渠道被滤", "ch-filter-1")
    await make_pc_user(session_factory, "正式被留", "pc-filter")

    resp = await client.get(BASE + "/admin/users", params={"channel": "ACCOUNT"}, headers=headers)
    assert resp.json()["code"] == 0
    channels = {u["channel"] for u in resp.json()["data"]["list"]}
    assert channels == {"ACCOUNT"}
    assert "正式被留" in {u["name"] for u in resp.json()["data"]["list"]}

    resp = await client.get(BASE + "/admin/users", headers=headers)
    names = {u["name"] for u in resp.json()["data"]["list"]}
    assert "渠道被滤" in names  # 不带过滤参数时接口语义不变（渠道身份页等内部调用方依赖全量）


# ---- 二期：同名线索与挂接记录 ----

async def test_unlinked_list_carries_same_name_suspects(client, session_factory):
    """挂接防错线索：待归一列表每行附同名 PC 用户（suspects）——
    仅完全同名、仅正式 ACTIVE 用户；已归一列表不带；同名临时人不作疑似。"""
    headers = await admin_headers(client, session_factory, account="boss-suspect")
    await channel_login(client, "同名张三", "ch-suspect-1")
    await channel_login(client, "查无此人", "ch-suspect-2")
    pc = await make_pc_user(session_factory, "同名张三", "pc-suspect")
    disabled_pc = await make_pc_user(session_factory, "查无此人", "pc-suspect-off")
    async with session_factory() as db:
        async with db.begin():
            (await db.execute(select(User).where(User.id == disabled_pc.id))).scalar_one().status = "DISABLED"

    resp = await client.get(BASE + "/admin/channel-identities", params={"linked": "false"}, headers=headers)
    assert resp.json()["code"] == 0
    rows = {i["channelUserName"]: i for i in resp.json()["data"]["list"]}
    suspects = rows["同名张三"]["suspects"]
    assert [s["id"] for s in suspects] == [pc.id]
    assert suspects[0]["loginAccount"] == "pc-suspect"
    assert rows["查无此人"]["suspects"] == []  # 同名 PC 用户已停用，不作疑似（挂接目标必须 ACTIVE）

    linked = await client.get(BASE + "/admin/channel-identities", params={"linked": "true"}, headers=headers)
    assert all("suspects" not in i for i in linked.json()["data"]["list"])


async def test_link_logs_api_paginates_link_and_rebind(client, session_factory):
    """挂接记录 Tab：审计分页出参——LINK 带过户明细、REBIND movedCounts 为空，倒序。"""
    headers = await admin_headers(client, session_factory, account="boss-logs")
    await channel_login(client, "记录用户", "ch-log-1")
    pc_a = await make_pc_user(session_factory, "甲用户", "pc-log-a")
    pc_b = await make_pc_user(session_factory, "乙用户", "pc-log-b")
    identity_id = (await client.get(BASE + "/admin/channel-identities",
                                    params={"linked": "false", "keyword": "ch-log-1"},
                                    headers=headers)).json()["data"]["list"][0]["id"]
    linked = await client.post(f"{BASE}/admin/users/{pc_a.id}/channel-identities",
                               json={"identityId": identity_id}, headers=headers)
    assert linked.json()["code"] == 0
    rebound = await client.post(f"{BASE}/admin/channel-identities/{identity_id}/rebind",
                                json={"userId": pc_b.id}, headers=headers)
    assert rebound.json()["code"] == 0

    resp = await client.get(BASE + "/admin/identity-link-logs", params={"page": 1, "size": 10},
                            headers=headers)
    body = resp.json()["data"]
    logs = body["list"]
    assert body["total"] == 2
    assert [log["action"] for log in logs] == ["REBIND", "LINK"]  # 倒序：最新的在前
    rebind_log, link_log = logs
    assert link_log["fromUserName"] == "记录用户" and link_log["toUserName"] == "甲用户"
    assert link_log["movedCounts"] is None or isinstance(link_log["movedCounts"], dict)
    assert link_log["operatorName"] == "管理员"
    assert rebind_log["fromUserName"] == "甲用户" and rebind_log["toUserName"] == "乙用户"
    assert rebind_log["movedCounts"] is None  # 改挂不搬数据，无过户明细
