"""P1 账密登录/角色权限/用户管理 单测：登录锁定、强制改密、refresh 旋转吊销、越权 403、重置密码、脱敏。"""
import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models import User

BASE = "/demandhub-api"


def make_user(**kw):
    defaults = dict(name="账密用户", wecom_userid="acct:u1", channel="ACCOUNT", role="HANDLER",
                    login_account="u1", password_hash=hash_password("Passw0rd!"), must_change_pwd=False)
    defaults.update(kw)
    return User(**defaults)


@pytest.fixture
async def handler(session_factory):
    async with session_factory() as db:
        async with db.begin():
            user = make_user()
            db.add(user)
            await db.flush()
        return user


@pytest.fixture
async def admin(session_factory):
    async with session_factory() as db:
        async with db.begin():
            user = make_user(name="管理员", wecom_userid="acct:boss", login_account="boss", role="ADMIN")
            db.add(user)
            await db.flush()
        return user


async def login(client, account, password="Passw0rd!"):
    return await client.post(f"{BASE}/auth/login", json={"loginAccount": account, "password": password})


def bearer(token):
    return {"Authorization": "Bearer " + token}


# ---------- 账密登录 ----------

async def test_login_success_returns_dual_token(client, handler):
    resp = await login(client, "u1")
    data = resp.json()["data"]
    assert data["accessToken"] and data["refreshToken"]
    assert data["user"]["role"] == "HANDLER"
    assert data["mustChangePwd"] is False


async def test_login_unknown_account_same_message_as_wrong_password(client, handler):
    unknown = await login(client, "no-such-user")
    wrong_pwd = await login(client, "u1", "bad-password")
    assert unknown.json()["code"] == 1115 == wrong_pwd.json()["code"]
    assert unknown.json()["message"] == wrong_pwd.json()["message"]


async def test_login_locks_after_five_failures(client, handler):
    for _ in range(5):
        resp = await login(client, "u1", "bad-password")
        assert resp.json()["code"] == 1115
    locked = await login(client, "u1")
    assert locked.json()["code"] == 1116  # 锁定期间即使密码正确也拒绝


async def test_login_success_resets_fail_count(client, handler, session_factory):
    for _ in range(4):
        await login(client, "u1", "bad-password")
    assert (await login(client, "u1")).json()["code"] == 0
    async with session_factory() as db:
        user = (await db.execute(select(User).where(User.login_account == "u1"))).scalar_one()
        assert user.fail_count == 0 and user.locked_until is None


async def test_disabled_account_cannot_login(client, session_factory):
    async with session_factory() as db:
        async with db.begin():
            db.add(make_user(status="DISABLED"))
    resp = await login(client, "u1")
    assert resp.json()["code"] == 1113


# ---------- 强制改密 ----------

async def test_must_change_pwd_flow(client, session_factory):
    async with session_factory() as db:
        async with db.begin():
            db.add(make_user(must_change_pwd=True))
    data = (await login(client, "u1")).json()["data"]
    assert data["mustChangePwd"] is True
    change = await client.post(f"{BASE}/auth/change-password",
                               json={"oldPassword": "Passw0rd!", "newPassword": "NewPass123"},
                               headers=bearer(data["accessToken"]))
    assert change.json()["code"] == 0
    relogin = await login(client, "u1", "NewPass123")
    assert relogin.json()["data"]["mustChangePwd"] is False
    # 改密后旧 refresh token 全部吊销
    reuse = await client.post(f"{BASE}/auth/refresh", json={"refreshToken": data["refreshToken"]})
    assert reuse.json()["code"] == 1117


async def test_change_password_rejects_wrong_old(client, handler):
    data = (await login(client, "u1")).json()["data"]
    resp = await client.post(f"{BASE}/auth/change-password",
                             json={"oldPassword": "wrong-old", "newPassword": "NewPass123"},
                             headers=bearer(data["accessToken"]))
    assert resp.json()["code"] == 1118


# ---------- refresh 旋转与登出 ----------

async def test_refresh_rotates_and_revokes_old(client, handler):
    data = (await login(client, "u1")).json()["data"]
    first = await client.post(f"{BASE}/auth/refresh", json={"refreshToken": data["refreshToken"]})
    assert first.json()["code"] == 0
    replay = await client.post(f"{BASE}/auth/refresh", json={"refreshToken": data["refreshToken"]})
    assert replay.json()["code"] == 1117  # 旧票旋转后重放即拒
    second = await client.post(f"{BASE}/auth/refresh",
                               json={"refreshToken": first.json()["data"]["refreshToken"]})
    assert second.json()["code"] == 0


async def test_logout_revokes_refresh_token(client, handler):
    data = (await login(client, "u1")).json()["data"]
    assert (await client.post(f"{BASE}/auth/logout",
                              json={"refreshToken": data["refreshToken"]})).json()["code"] == 0
    reuse = await client.post(f"{BASE}/auth/refresh", json={"refreshToken": data["refreshToken"]})
    assert reuse.json()["code"] == 1117


async def test_me_returns_role(client, handler):
    data = (await login(client, "u1")).json()["data"]
    me = await client.get(f"{BASE}/auth/me", headers=bearer(data["accessToken"]))
    assert me.json()["data"]["role"] == "HANDLER"
    assert me.json()["data"]["mustChangePwd"] is False


# ---------- 用户管理（仅 ADMIN） ----------

async def admin_headers(client):
    data = (await login(client, "boss")).json()["data"]
    return bearer(data["accessToken"])


async def test_users_api_forbidden_for_handler(client, handler, admin):
    data = (await login(client, "u1")).json()["data"]
    resp = await client.get(f"{BASE}/admin/users", headers=bearer(data["accessToken"]))
    assert resp.json()["code"] == 403
    create = await client.post(f"{BASE}/admin/users", headers=bearer(data["accessToken"]),
                               json={"loginAccount": "x1", "name": "x", "initialPassword": "Abcd1234"})
    assert create.json()["code"] == 403


async def test_create_user_and_masked_list(client, admin, session_factory):
    async with session_factory() as db:
        async with db.begin():
            db.add(make_user(phone="13812345678", email="zhangsan@example.com"))
    headers = await admin_headers(client)
    created = await client.post(f"{BASE}/admin/users", headers=headers,
                                json={"loginAccount": "new1", "name": "新人",
                                      "initialPassword": "Abcd1234", "role": "HANDLER",
                                      "types": ["TECH"], "phone": "13900002001"})
    body = created.json()
    assert body["code"] == 0
    assert body["data"]["mustChangePwd"] is True
    assert "passwordHash" not in body["data"] and "password_hash" not in body["data"]
    dup = await client.post(f"{BASE}/admin/users", headers=headers,
                            json={"loginAccount": "new1", "name": "新人", "initialPassword": "Abcd1234",
                                  "phone": "13900002002"})
    assert dup.json()["code"] == 1120
    listing = await client.get(f"{BASE}/admin/users?keyword=u1", headers=headers)
    row = listing.json()["data"]["list"][0]
    assert row["phone"] == "138****5678"
    assert row["email"] == "z***@example.com"
    assert listing.json()["data"]["total"] == 1


async def test_phone_required_unique_and_login_by_phone(client, admin):
    """手机号：新建必填、格式校验、全表判重（1129）、可作登录账号；登录账号优先于手机号。"""
    headers = await admin_headers(client)
    # 必填：缺 phone → 400
    missing = await client.post(f"{BASE}/admin/users", headers=headers,
                                json={"loginAccount": "p1", "name": "缺手机",
                                      "initialPassword": "Abcd1234", "types": ["TECH"]})
    assert missing.json()["code"] == 400
    # 格式：非 11 位手机号 → 400
    bad_fmt = await client.post(f"{BASE}/admin/users", headers=headers,
                                json={"loginAccount": "p1", "name": "错格式",
                                      "initialPassword": "Abcd1234", "types": ["TECH"],
                                      "phone": "12345"})
    assert bad_fmt.json()["code"] == 400
    # 邮箱选填，但填了须合法
    bad_mail = await client.post(f"{BASE}/admin/users", headers=headers,
                                 json={"loginAccount": "p1", "name": "错邮箱",
                                       "initialPassword": "Abcd1234", "types": ["TECH"],
                                       "phone": "13900003001", "email": "not-an-email"})
    assert bad_mail.json()["code"] == 400
    created = await client.post(f"{BASE}/admin/users", headers=headers,
                                json={"loginAccount": "p1", "name": "手机用户",
                                      "initialPassword": "Abcd1234", "types": ["TECH"],
                                      "phone": "13900003001", "email": "phone.user@example.com"})
    assert created.json()["code"] == 0
    assert created.json()["data"]["phone"] == "139****3001"  # 出参脱敏
    # 手机号判重 → 1129
    dup_phone = await client.post(f"{BASE}/admin/users", headers=headers,
                                  json={"loginAccount": "p2", "name": "撞手机",
                                        "initialPassword": "Abcd1234", "types": ["TECH"],
                                        "phone": "13900003001"})
    assert dup_phone.json()["code"] == 1129
    # 手机号可作登录账号（must_change_pwd 用户先走改密链路也能拿到 token）
    by_phone = await login(client, "13900003001", "Abcd1234")
    assert by_phone.json()["code"] == 0
    assert by_phone.json()["data"]["user"]["id"] == created.json()["data"]["id"]
    # 登录账号优先：手机号与他人登录账号撞串时，进入登录账号的主人
    clash = await client.post(f"{BASE}/admin/users", headers=headers,
                              json={"loginAccount": "13900003002", "name": "账号撞号",
                                    "initialPassword": "Abcd1234", "types": ["TECH"],
                                    "phone": "13900003003"})
    assert clash.json()["code"] == 0
    by_login = await login(client, "13900003002", "Abcd1234")
    assert by_login.json()["data"]["user"]["id"] == clash.json()["data"]["id"]


async def test_disable_blocks_login_and_revokes_refresh(client, admin):
    await client.post(f"{BASE}/admin/users", headers=await admin_headers(client),
                      json={"loginAccount": "v1", "name": "v", "initialPassword": "Abcd1234",
                            "types": ["TECH"], "phone": "13900002003"})
    data = (await login(client, "v1", "Abcd1234")).json()["data"]
    target = (await client.get(f"{BASE}/admin/users?keyword=v1",
                               headers=await admin_headers(client))).json()["data"]["list"][0]
    resp = await client.put(f"{BASE}/admin/users/{target['id']}/disable", headers=await admin_headers(client))
    assert resp.json()["data"]["status"] == "DISABLED"
    assert (await login(client, "v1", "Abcd1234")).json()["code"] == 1113
    refresh = await client.post(f"{BASE}/auth/refresh", json={"refreshToken": data["refreshToken"]})
    assert refresh.json()["code"] == 1117
    activate = await client.put(f"{BASE}/admin/users/{target['id']}/activate", headers=await admin_headers(client))
    assert activate.json()["data"]["status"] == "ACTIVE"


async def test_cannot_disable_or_reset_self(client, admin):
    headers = await admin_headers(client)
    me = (await client.get(f"{BASE}/auth/me", headers=headers)).json()["data"]
    assert (await client.put(f"{BASE}/admin/users/{me['id']}/disable", headers=headers)).json()["code"] == 400
    reset = await client.post(f"{BASE}/admin/users/{me['id']}/reset-password",
                              json={"newPassword": "Abcd1234"}, headers=headers)
    assert reset.json()["code"] == 400


async def test_reset_password_forces_change_and_revokes(client, admin):
    await client.post(f"{BASE}/admin/users", headers=await admin_headers(client),
                      json={"loginAccount": "w1", "name": "w", "initialPassword": "Abcd1234",
                            "types": ["TECH"], "phone": "13900002004"})
    old = (await login(client, "w1", "Abcd1234")).json()["data"]
    target = (await client.get(f"{BASE}/admin/users?keyword=w1",
                               headers=await admin_headers(client))).json()["data"]["list"][0]
    reset = await client.post(f"{BASE}/admin/users/{target['id']}/reset-password",
                              json={"newPassword": "Reset1234"}, headers=await admin_headers(client))
    assert reset.json()["code"] == 0
    replay = await client.post(f"{BASE}/auth/refresh", json={"refreshToken": old["refreshToken"]})
    assert replay.json()["code"] == 1117
    relogin = (await login(client, "w1", "Reset1234")).json()["data"]
    assert relogin["mustChangePwd"] is True

