import hashlib
import json

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.api.auth import ChannelParameters
from app.config import Settings, get_settings
from app.db.models import Base, User
from app.main import create_app

PATH = "/demandhub-api/auth/channel-parameters"
HOST_TOKEN = "synthetic-host-token-never-persist-or-echo"
PAYLOAD = {"userid": "host-user", "authToken": HOST_TOKEN,
           "userName": "联调用户", "department": "零售部门"}


@pytest_asyncio.fixture
async def parameters_client(session_factory, monkeypatch):
    monkeypatch.setenv("AUTH_DEV_LOGIN", "false")
    monkeypatch.setenv("CHANNEL_ENTRY_AUTH_MODE", "trusted_parameters")
    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=create_app(), raise_app_exceptions=False), base_url="http://test") as client:
        yield client
    get_settings.cache_clear()


def test_mode_defaults_to_ticket():
    settings = Settings(_env_file=None, auth_dev_login=False)
    assert settings.channel_entry_auth_mode == "ticket"


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_trusted_mode_rejected_outside_test(environment):
    with pytest.raises(ValidationError, match="参数联调认证仅允许在测试环境启用"):
        Settings(_env_file=None, app_env=environment, auth_dev_login=False,
                 channel_entry_auth_mode="trusted_parameters")


def test_trusted_mode_rejects_dev_login():
    with pytest.raises(ValidationError, match="参数联调认证禁止同时启用 dev-login"):
        Settings(_env_file=None, app_env="test", auth_dev_login=True,
                 channel_entry_auth_mode="trusted_parameters")


@pytest.mark.parametrize("environment", ["test", "dev", "prod"])
async def test_ticket_mode_has_no_parameters_route(environment):
    settings = Settings(_env_file=None, app_env=environment, auth_dev_login=False)
    async with AsyncClient(transport=ASGITransport(app=create_app(settings)), base_url="http://test") as client:
        response = await client.post(PATH, json=PAYLOAD)
        assert response.status_code == 404


async def test_parameters_mode_no_dev_login_and_ticket_compatible(parameters_client, monkeypatch):
    assert (await parameters_client.post("/demandhub-api/auth/dev-login", json={})).status_code == 404
    from app.api import auth
    from app.sso.schemas import SsoProfile
    class StubSso:
        async def verify(self, ticket):
            assert ticket == "synthetic-ticket"
            return SsoProfile(user_id="ticket-user", name="票据用户")
    monkeypatch.setattr(auth, "get_sso_client", lambda: StubSso())
    result = await parameters_client.get("/demandhub-api/auth/channel-sso",
        params={"channel": "chuangjinls", "ticket": "synthetic-ticket"})
    assert result.json()["code"] == 0
    assert result.json()["data"]["user"]["userId"] == "ticket-user"


@pytest.mark.parametrize("patch", [
    {"userid": ""}, {"userid": "  "}, {"userid": "a" * 65}, {"userid": 1},
    {"authToken": ""}, {"authToken": " \n "}, {"authToken": "x" * 4097},
    {"userName": ""}, {"userName": " "}, {"userName": "名" * 65},
    {"department": "部" * 129}, {"auth_token": HOST_TOKEN},
    {"user_name": "别名"}, {"role": "ADMIN"},
])
async def test_input_validation(parameters_client, patch, caplog):
    response = await parameters_client.post(PATH, json={**PAYLOAD, **patch})
    assert response.status_code == 200 and response.json()["code"] == 400
    assert HOST_TOKEN not in response.text + caplog.text


@pytest.mark.parametrize("required", ["userid", "authToken", "userName"])
async def test_required_parameters(parameters_client, required):
    payload = {key: value for key, value in PAYLOAD.items() if key != required}
    response = await parameters_client.post(PATH, json=payload)
    assert response.json()["code"] == 400 and HOST_TOKEN not in response.text


async def test_same_identity_updates_display_fields_and_no_token_storage(parameters_client, session_factory, caplog):
    first = await parameters_client.post(PATH, json={**PAYLOAD, "userid": " host-user ", "userName": " 联调用户 "})
    assert first.json()["code"] == 0
    original = first.json()["data"]
    assert original["user"]["userId"] == "host-user" and original["user"]["name"] == "联调用户"
    assert original["user"]["deptName"] == "零售部门"
    second = await parameters_client.post(PATH, json={**PAYLOAD, "authToken": "any-other-synthetic-host-token",
        "userName": "更新姓名", "department": "更新部门"})
    updated = second.json()["data"]
    assert updated["user"]["id"] == original["user"]["id"]
    assert updated["user"]["name"] == "更新姓名" and updated["user"]["deptName"] == "更新部门"
    claims = jwt.decode(updated["accessToken"], get_settings().jwt_secret, algorithms=["HS256"])
    assert claims["uid"] == "host-user" and claims["name"] == "更新姓名"
    me = await parameters_client.get("/demandhub-api/auth/me",
        headers={"Authorization": "Bearer " + updated["accessToken"]})
    assert me.json()["data"]["deptName"] == "更新部门"
    async with session_factory() as db:
        records = []
        for table in Base.metadata.sorted_tables:
            records.extend(dict(row) for row in (await db.execute(select(table))).mappings())
    all_data = json.dumps(records, ensure_ascii=False, default=str)
    digest = hashlib.sha256(HOST_TOKEN.encode()).hexdigest()
    assert HOST_TOKEN not in all_data + first.text + second.text + json.dumps(claims) + caplog.text
    assert digest not in all_data + first.text + second.text + caplog.text
    assert "authToken" not in all_data + first.text + second.text
    assert "auth_token" not in repr(ChannelParameters.model_validate(PAYLOAD))
    assert HOST_TOKEN not in repr(ChannelParameters.model_validate(PAYLOAD))
    with pytest.raises(ValidationError) as exc:
        ChannelParameters.model_validate({**PAYLOAD, "authToken": HOST_TOKEN * 200})
    assert HOST_TOKEN not in str(exc.value)


async def test_disabled_user_cannot_be_reenabled(parameters_client, session_factory):
    response = await parameters_client.post(PATH, json=PAYLOAD)
    user_id = response.json()["data"]["user"]["id"]
    issued = response.json()["data"]["accessToken"]
    async with session_factory() as db:
        async with db.begin():
            user = await db.get(User, user_id)
            user.status = "DISABLED"
    rejected = await parameters_client.post(PATH, json={**PAYLOAD, "userName": "重新登录"})
    assert rejected.json()["code"] == 1113
    async with session_factory() as db:
        user = await db.get(User, user_id)
        assert user.status == "DISABLED" and user.name == "联调用户"
    assert (await parameters_client.get("/demandhub-api/auth/me",
        headers={"Authorization": "Bearer " + issued})).status_code == 401


async def test_only_userid_whitelist_grants_admin(parameters_client):
    ordinary = await parameters_client.post(PATH, json={**PAYLOAD, "userName": "管理员",
        "department": "ADMIN", "authToken": "mvp-admin"})
    ordinary_data = ordinary.json()["data"]
    assert ordinary_data["user"]["isAdmin"] is False
    denied = await parameters_client.get("/demandhub-api/admin/demand/list",
        headers={"Authorization": "Bearer " + ordinary_data["accessToken"]})
    assert denied.json()["code"] == 403
    admin = await parameters_client.post(PATH, json={**PAYLOAD, "userid": "mvp-admin", "department": None})
    assert admin.json()["data"]["user"]["isAdmin"] is True
    assert admin.json()["data"]["user"]["deptName"] is None


async def test_known_max_lengths_and_optional_department(parameters_client):
    response = await parameters_client.post(PATH, json={"userid": "u" * 64,
        "authToken": "t" * 4096, "userName": "名" * 64, "department": "部" * 128})
    assert response.json()["code"] == 0
    missing_department = await parameters_client.post(PATH, json={key: value for key, value in PAYLOAD.items() if key != "department"})
    assert missing_department.json()["code"] == 0
    assert missing_department.json()["data"]["user"]["deptName"] is None


async def test_unexpected_failure_does_not_echo_or_log_host_token(parameters_client, monkeypatch, caplog):
    from app.api import auth
    async def fail(db, profile):
        assert "authToken" not in profile.model_dump() and "auth_token" not in profile.model_dump()
        raise RuntimeError(HOST_TOKEN)
    monkeypatch.setattr(auth, "upsert_from_sso", fail)
    response = await parameters_client.post(PATH, json=PAYLOAD)
    assert response.json()["code"] == 500
    assert HOST_TOKEN not in response.text + caplog.text
