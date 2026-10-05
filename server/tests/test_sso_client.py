import json

import httpx
import pytest

from app.core.errors import BizError
from app.sso.chuangjin_ls import ChuangjinLsSsoClient
from app.sso.schemas import ChannelSsoConfig
from app.sso.sign import VERIFY_PATH, hmac_sha256_hex, mask_phone, mask_ticket, string_to_sign


@pytest.fixture
def sso():
    return ChuangjinLsSsoClient(ChannelSsoConfig(base_url="http://sso.test", app_key="test-app", app_secret="fake-test-secret", timeout_ms=10))


def success():
    return {"errcode": 0, "user": {"user_id": "u1", "name": "用户", "phone": "13800001111", "dept_id": "d1", "dept_name": "部门", "dept_path": "总部/部门", "employee_no": "e1", "email": "u@example.test"}}


async def test_success_maps_profile_fields(sso, respx_mock):
    route = respx_mock.post("http://sso.test" + VERIFY_PATH).respond(200, json=success())
    profile = await sso.verify('quoted"ticket')
    assert profile.user_id == "u1" and profile.dept_name == "部门" and profile.phone == "13800001111"
    request = route.calls[0].request
    assert json.loads(request.content) == {"ticket": 'quoted"ticket'}
    assert request.headers["X-Sign"] == hmac_sha256_hex(sso.config.app_secret, string_to_sign(VERIFY_PATH, "test-app", request.headers["X-Timestamp"], request.headers["X-Nonce"], request.content.decode()))


@pytest.mark.parametrize("upstream,expected", [(40001,1107),(40002,1107),(40003,1102),(40004,1113),(40005,1107),(50000,1102)])
async def test_upstream_error_mapping(sso, respx_mock, upstream, expected):
    respx_mock.post("http://sso.test" + VERIFY_PATH).respond(200, json={"errcode": upstream, "errmsg": "sensitive upstream text"})
    with pytest.raises(BizError) as exc:
        await sso.verify("ticket")
    assert exc.value.code == expected and "sensitive" not in exc.value.message


async def test_success_missing_user_id(sso, respx_mock):
    respx_mock.post("http://sso.test" + VERIFY_PATH).respond(200, json={"errcode": 0, "user": {"name": "用户"}})
    with pytest.raises(BizError) as exc:
        await sso.verify("ticket")
    assert exc.value.code == 1102


@pytest.mark.parametrize("response", [httpx.Response(503), httpx.Response(200, text="not json")])
async def test_http_or_format_failure(sso, respx_mock, response):
    respx_mock.post("http://sso.test" + VERIFY_PATH).mock(return_value=response)
    with pytest.raises(BizError) as exc:
        await sso.verify("ticket")
    assert exc.value.code == 1102 and sso.consecutive_failures == 1


async def test_timeout_no_retry_and_breaker(sso, respx_mock):
    route = respx_mock.post("http://sso.test" + VERIFY_PATH).mock(side_effect=httpx.ReadTimeout("secret"))
    for _ in range(4):
        with pytest.raises(BizError):
            await sso.verify("ticket")
    assert route.call_count == 3


async def test_blank_ticket_rejected(sso, respx_mock):
    with pytest.raises(BizError) as exc:
        await sso.verify(" ")
    assert exc.value.code == 1107 and not respx_mock.calls


def test_sign_matches_contract_mock():
    from tests.contract_mock import APP_KEY, APP_SECRET, expected_sign
    body = '{"ticket":"test-ticket"}'
    assert hmac_sha256_hex(APP_SECRET, string_to_sign(VERIFY_PATH, APP_KEY, "123", "nonce", body)) == expected_sign("123", "nonce", body)
    assert mask_ticket("abcdef") == "abcd***" and mask_phone("13800001111") == "138****1111"
