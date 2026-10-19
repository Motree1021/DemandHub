"""渠道白名单单测（2026-10-16 方案定稿）。

- 服务层：添加（重复/格式/渠道缺失守卫）、批量（重复/无效/已存在分组）、启停/移除（留痕+404）、
  开关与联系引导（变更才落痕）、待登记清单
- 登录拦截：开关关闭=全放行；开启仅 ENABLED 放行、未命中 1123 且不建档；dev-login 不受控
- API 守卫：非 ADMIN 403；公开联系引导接口无登录态可读
"""
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.core.errors import BizError, ErrorCode
from app.db.models import DemandChannel, DemandChannelWhitelist, DemandChannelWhitelistLog, User
from app.main import create_app
from app.services import whitelist_service as service

CH = "CHUANGJIN_LS"
PARAMS_PATH = "/demandhub-api/auth/channel-parameters"


async def _seed_channel(db, *, enabled=0, contact=None):
    db.add(DemandChannel(channel_code=CH, channel_name="创金零售", status="ACTIVE",
                         whitelist_enabled=enabled, whitelist_contact=contact))


async def _operator(db, userid="wl-admin"):
    user = User(name="白名单管理员", wecom_userid=userid, channel=CH)
    db.add(user)
    await db.flush()
    return user


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest_asyncio.fixture
async def parameters_client(session_factory, monkeypatch):
    monkeypatch.setenv("AUTH_DEV_LOGIN", "false")
    monkeypatch.setenv("CHANNEL_ENTRY_AUTH_MODE", "trusted_parameters")
    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=create_app(), raise_app_exceptions=False),
                           base_url="http://test") as client:
        yield client
    get_settings.cache_clear()


# ---------- 服务层：添加 / 批量 ----------

async def test_add_entry_guards(session_factory):
    async with session_factory() as db:
        async with db.begin():
            await _seed_channel(db)
            operator = await _operator(db)
            row = await service.add_entry(db, CH, channel_user_id="zhang.wei01",
                                          display_name="张伟", operator=operator)
            assert row.status == service.ENABLED and row.created_by == operator.id
            # 重复添加（大小写不敏感由 DB 唯一键 collation 保证，此处同值）
            with pytest.raises(BizError) as dup:
                await service.add_entry(db, CH, channel_user_id="zhang.wei01",
                                        display_name=None, operator=operator)
            assert dup.value.error_code == ErrorCode.WHITELIST_ENTRY_DUPLICATED
            with pytest.raises(BizError) as bad:
                await service.add_entry(db, CH, channel_user_id="bad id!",
                                        display_name=None, operator=operator)
            assert bad.value.error_code == ErrorCode.PARAM_INVALID
            with pytest.raises(BizError) as missing:
                await service.add_entry(db, "NO_SUCH", channel_user_id="a01",
                                        display_name=None, operator=operator)
            assert missing.value.error_code == ErrorCode.NOT_FOUND
            logs = (await db.execute(select(DemandChannelWhitelistLog))).scalars().all()
            assert len(logs) == 1 and logs[0].action == service.ADD and logs[0].detail == "张伟"


async def test_batch_add_grouping(session_factory):
    async with session_factory() as db:
        async with db.begin():
            await _seed_channel(db)
            operator = await _operator(db)
            await service.add_entry(db, CH, channel_user_id="a01", display_name=None, operator=operator)
            result = await service.add_batch(db, CH, entries=[
                {"channel_user_id": "b02", "display_name": "李娜"},
                {"channel_user_id": "b03", "display_name": None},
                {"channel_user_id": "B03", "display_name": None},   # 批量内自身重复（大小写不敏感）
                {"channel_user_id": "a01", "display_name": None},   # 已存在
                {"channel_user_id": "bad id", "display_name": None},  # 格式无效
            ], operator=operator)
            assert result["added"] == 2 and result["addedIds"] == ["b02", "b03"]
            assert result["duplicated"] == ["B03", "a01"] and result["invalid"] == ["bad id"]
            entries = (await db.execute(select(DemandChannelWhitelist))).scalars().all()
            assert {e.channel_user_id for e in entries} == {"a01", "b02", "b03"}
            logs = (await db.execute(select(DemandChannelWhitelistLog)
                                     .where(DemandChannelWhitelistLog.detail.like("批量添加%")))).scalars().all()
            assert len(logs) == 2  # 批量添加逐条留痕


# ---------- 服务层：启停 / 移除 / 开关 ----------

async def test_status_remove_and_config(session_factory):
    async with session_factory() as db:
        async with db.begin():
            await _seed_channel(db)
            operator = await _operator(db)
            row = await service.add_entry(db, CH, channel_user_id="c04", display_name="陈静",
                                          operator=operator)
            with pytest.raises(BizError):
                await service.update_entry_status(db, row.id, status="ENABLED", operator=operator)  # 未变化
            row = await service.update_entry_status(db, row.id, status="DISABLED", operator=operator)
            assert row.status == service.DISABLED
            with pytest.raises(BizError):
                await service.update_entry_status(db, 999999, status="ENABLED", operator=operator)

            channel = await service.update_config(db, CH, enabled=True, contact=None, operator=operator)
            assert channel.whitelist_enabled == 1
            channel = await service.update_config(db, CH, enabled=True, contact="请联系管理员", operator=operator)
            assert channel.whitelist_contact == "请联系管理员"
            channel = await service.update_config(db, CH, enabled=False, contact="", operator=operator)
            assert channel.whitelist_enabled == 0 and channel.whitelist_contact is None  # 空串=清空

            await service.remove_entry(db, row.id, operator=operator)
            with pytest.raises(BizError):
                await service.remove_entry(db, row.id, operator=operator)

            actions = [log.action for log in (await db.execute(
                select(DemandChannelWhitelistLog).order_by(DemandChannelWhitelistLog.id))).scalars().all()]
            assert actions == [service.ADD, service.DISABLE, service.SWITCH_ON,
                               service.UPDATE_CONTACT, service.SWITCH_OFF,
                               service.UPDATE_CONTACT, service.REMOVE]
            remove_log = (await db.execute(select(DemandChannelWhitelistLog)
                                           .where(DemandChannelWhitelistLog.action == service.REMOVE))
                          ).scalars().one()
            assert "c04（陈静）" in remove_log.detail  # 移除快照


# ---------- 登录拦截 ----------

async def test_parameters_login_gating(parameters_client, session_factory):
    async with session_factory() as db:
        async with db.begin():
            await _seed_channel(db, enabled=1, contact="请联系张敏")
            db.add(DemandChannelWhitelist(channel_code=CH, channel_user_id="vip-user",
                                          display_name="贵宾", status="ENABLED"))
            db.add(DemandChannelWhitelist(channel_code=CH, channel_user_id="stopped-user",
                                          display_name="停用", status="DISABLED"))

    payload = {"userid": "host-user", "authToken": "tok", "userName": "未登记用户"}
    blocked = await parameters_client.post(PARAMS_PATH, json=payload)
    assert blocked.json()["code"] == 1123
    assert blocked.json()["message"] == "非白名单用户，暂不支持访问"
    async with session_factory() as db:  # 被拦不建档
        assert (await db.execute(select(User).where(User.wecom_userid == "host-user"))).scalar_one_or_none() is None

    stopped = await parameters_client.post(PARAMS_PATH, json={**payload, "userid": "stopped-user"})
    assert stopped.json()["code"] == 1123  # DISABLED 条目不放行

    allowed = await parameters_client.post(PARAMS_PATH, json={**payload, "userid": "vip-user"})
    assert allowed.json()["code"] == 0
    assert allowed.json()["data"]["user"]["userId"] == "vip-user"

    contact = await parameters_client.get("/demandhub-api/auth/whitelist-contact")
    assert contact.json()["data"]["contact"] == "请联系张敏"

    # 开关关闭=全放行
    async with session_factory() as db:
        async with db.begin():
            channel = (await db.execute(select(DemandChannel).where(
                DemandChannel.channel_code == CH))).scalar_one()
            channel.whitelist_enabled = 0
    open_pass = await parameters_client.post(PARAMS_PATH, json={**payload, "userid": "host-user2"})
    assert open_pass.json()["code"] == 0


async def test_dev_login_not_gated(client, session_factory):
    async with session_factory() as db:
        async with db.begin():
            await _seed_channel(db, enabled=1)
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": "开发用户", "wecomUserid": "dev-not-in-whitelist"})
    assert response.status_code == 200 and response.json()["code"] == 0  # dev-login 不受白名单约束


# ---------- 管理 API ----------

async def test_admin_api_flow(client, session_factory, admin_headers):
    user_headers = await _login(client, "普通用户", "wl-normal-user")
    async with session_factory() as db:
        async with db.begin():
            await _seed_channel(db)

    base = f"/demandhub-api/admin/channels/{CH}/whitelist"
    assert (await client.get(base, headers=user_headers)).json()["code"] == 403  # 非 ADMIN

    added = await client.post(base, headers=admin_headers,
                              json={"channelUserId": "zhang.wei01", "displayName": "张伟"})
    assert added.json()["code"] == 0 and added.json()["data"]["status"] == "ENABLED"
    entry_id = added.json()["data"]["id"]

    dup = await client.post(base, headers=admin_headers, json={"channelUserId": "zhang.wei01"})
    assert dup.json()["code"] == 1125

    batch = await client.post(f"{base}/batch", headers=admin_headers, json={"entries": [
        {"channelUserId": "li.na02", "displayName": "李娜"},
        {"channelUserId": "zhang.wei01"},
        {"channelUserId": "bad id"},
    ]})
    assert batch.json()["data"] == {"added": 1, "addedIds": ["li.na02"],
                                    "duplicated": ["zhang.wei01"], "invalid": ["bad id"]}

    listed = await client.get(f"{base}?keyword=zhang&status=ENABLED", headers=admin_headers)
    data = listed.json()["data"]
    assert data["total"] == 1 and data["list"][0]["channelUserId"] == "zhang.wei01"
    assert data["stats"] == {"enabled": 2, "disabled": 0}
    assert data["list"][0]["lastLoginAt"] is None  # 从未登录

    # 待登记：dev-login 自动建档的 wl-normal-user / mvp-admin 未入白名单
    pending = await client.get(f"{base}/pending", headers=admin_headers)
    pending_ids = {row["wecomUserid"] for row in pending.json()["data"]}
    assert "wl-normal-user" in pending_ids and "zhang.wei01" not in pending_ids

    disabled = await client.put(f"/demandhub-api/admin/channels/whitelist/{entry_id}/status",
                                headers=admin_headers, json={"status": "DISABLED"})
    assert disabled.json()["data"]["status"] == "DISABLED"

    config = await client.put(f"{base}/config", headers=admin_headers,
                              json={"whitelistEnabled": True, "whitelistContact": "请联系张敏"})
    assert config.json()["data"] == {"whitelistEnabled": True, "whitelistContact": "请联系张敏"}

    logs = await client.get(f"{base}/logs", headers=admin_headers)
    log_data = logs.json()["data"]
    assert log_data["total"] >= 5
    assert log_data["list"][0]["action"] == service.UPDATE_CONTACT  # 倒序
    assert {row["action"] for row in log_data["list"]} >= {
        service.ADD, service.DISABLE, service.SWITCH_ON, service.UPDATE_CONTACT}

    removed = await client.delete(f"/demandhub-api/admin/channels/whitelist/{entry_id}",
                                  headers=admin_headers)
    assert removed.json()["code"] == 0
