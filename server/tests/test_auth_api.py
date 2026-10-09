import asyncio
from datetime import datetime, timedelta, timezone

import jwt
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import get_settings
from app.db.models import User
from app.main import create_app

BASE = "/demandhub-api"


async def test_live_contract_sso(client):
    import httpx
    async with httpx.AsyncClient() as mock:
        ticket = (await mock.post("http://127.0.0.1:8199/ticket", json={"channelUserId": "real-contract-user", "name": "契约用户"})).json()["ticket"]
    response = await client.get(BASE + "/auth/channel-sso", params={"channel": "chuangjinls", "ticket": ticket})
    assert response.json()["code"] == 0
    assert response.json()["data"]["user"]["userId"] == "real-contract-user"
    replay = await client.get(BASE + "/auth/channel-sso", params={"channel": "chuangjinls", "ticket": ticket})
    assert replay.json()["code"] == 1107


async def test_concurrent_first_login_and_disabled_stays_disabled(client, session_factory):
    async def login():
        return await client.post(BASE + "/auth/dev-login", json={"name": "并发登录", "wecomUserid": "new-user"})
    responses = await asyncio.gather(*(login() for _ in range(10)))
    assert all(r.json()["code"] == 0 for r in responses)
    assert len({r.json()["data"]["user"]["id"] for r in responses}) == 1
    async with session_factory() as db:
        async with db.begin():
            user = (await db.execute(select(User).where(User.wecom_userid == "new-user"))).scalar_one()
            user.status = "DISABLED"
    response = await login()
    assert response.json()["code"] == 1113
    headers = {"Authorization": "Bearer " + responses[0].json()["data"]["accessToken"]}
    assert (await client.get(BASE + "/auth/me", headers=headers)).status_code == 401


async def test_test_login_only_admits_existing_users(client, session_factory):
    # 先经 dev-login 建档一个用户，test-login 只允许"已录入且姓名一致"的账号进入。
    await client.post(BASE + "/auth/dev-login", json={"name": "测试用户", "wecomUserid": "tester-001"})
    async with session_factory() as db:
        async with db.begin():
            before = len((await db.execute(select(User))).scalars().all())
    ok_resp = await client.post(BASE + "/auth/test-login", json={"name": "测试用户", "wecomUserid": "tester-001"})
    assert ok_resp.json()["code"] == 0
    assert ok_resp.json()["data"]["user"]["userId"] == "tester-001"
    # 姓名不匹配、账号未录入一律 1114，且不建档。
    assert (await client.post(BASE + "/auth/test-login", json={"name": "别人", "wecomUserid": "tester-001"})).json()["code"] == 1114
    assert (await client.post(BASE + "/auth/test-login", json={"name": "测试用户", "wecomUserid": "ghost"})).json()["code"] == 1114
    async with session_factory() as db:
        async with db.begin():
            after = (await db.execute(select(User))).scalars().all()
            assert len(after) == before
            (await db.execute(select(User).where(User.wecom_userid == "tester-001"))).scalar_one().status = "DISABLED"
    assert (await client.post(BASE + "/auth/test-login", json={"name": "测试用户", "wecomUserid": "tester-001"})).json()["code"] == 1113


async def test_test_login_route_gated_by_flag_and_env(client):
    settings = get_settings().model_copy(update={"auth_test_login": False})
    async with AsyncClient(transport=ASGITransport(app=create_app(settings)), base_url="http://flagoff") as app_off:
        assert (await app_off.post(BASE + "/auth/test-login", json={"name": "用户", "wecomUserid": "u"})).status_code == 404
    import pydantic
    import pytest
    with pytest.raises(pydantic.ValidationError):
        get_settings().model_validate({**get_settings().model_dump(), "app_env": "prod", "auth_test_login": True,
                                       "channel_ls_base_url": "http://x", "channel_ls_app_key": "k", "channel_ls_app_secret": "s"})


async def test_expired_token_and_prod_dev_route(client, auth_headers):
    token = jwt.decode(auth_headers["Authorization"][7:], get_settings().jwt_secret, algorithms=["HS256"])
    token["exp"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode(token, get_settings().jwt_secret, algorithm="HS256")
    assert (await client.get(BASE + "/auth/me", headers={"Authorization": "Bearer " + expired})).status_code == 401
    settings = get_settings().model_copy(update={"app_env": "prod", "auth_dev_login": False})
    async with AsyncClient(transport=ASGITransport(app=create_app(settings)), base_url="http://prod") as prod:
        assert (await prod.post(BASE + "/auth/dev-login", json={"name": "用户", "wecomUserid": "user"})).status_code == 404
        assert (await prod.get("/health")).status_code == 404
        assert (await prod.get(BASE + "/openapi.json")).status_code == 404
