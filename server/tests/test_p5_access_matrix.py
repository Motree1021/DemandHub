"""P5 系统管理域访问矩阵（验收证据）：

- 非 ADMIN（HANDLER）访问全部 P5 ADMIN 端点：HTTP 200 + body 业务码 403（统一响应体口径）
- ADMIN 访问全部 GET 端点放行（code=0）：证明守卫精确拦截而非全网拒绝

热重载不重启见 test_statemachine_admin.py（保存即热刷）；类型绑定状态机 key 校验见 test_types.py。
"""
import json

import pytest

VALID_JSON = json.dumps({"rules": [
    {"from": "DRAFT", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "提交"},
]}, ensure_ascii=False)

# (method, path, body)：POST/PUT 带最小合法 body，确保先过参数校验、由 require_admin 拦截
ADMIN_ONLY_CASES = [
    ("GET", "/admin/dicts", None),
    ("GET", "/admin/dicts/types", None),
    ("POST", "/admin/dicts", {"dictType": "G", "itemCode": "C", "itemName": "N"}),
    ("PUT", "/admin/dicts/1", {"itemName": "改名"}),
    ("GET", "/admin/types", None),
    ("POST", "/admin/types", {"typeCode": "XX", "typeName": "越权"}),
    ("PUT", "/admin/types/1", {"typeName": "越权"}),
    ("GET", "/admin/state-machines", None),
    ("GET", "/admin/state-machines/default-json", None),
    ("POST", "/admin/state-machines", {"configKey": "K1", "configName": "越权", "configJson": VALID_JSON}),
    ("PUT", "/admin/state-machines/1", {"configName": "越权"}),
    ("POST", "/admin/state-machines/reload", None),
    ("GET", "/admin/sla-configs", None),
    ("POST", "/admin/sla-configs", {"demandTypeCode": "TECH", "status": "TRIAGE",
                                    "warnMinutes": 10, "maxMinutes": 20}),
    ("PUT", "/admin/sla-configs/1", {"warnMinutes": 30}),
    ("DELETE", "/admin/sla-configs/1", None),
    ("GET", "/admin/channels", None),
    ("PUT", "/admin/channels/1/status", {"status": "DISABLED"}),
    ("GET", "/admin/channels/dept-unmapped", None),
    ("DELETE", "/admin/channels/dept-unmapped/1", None),
    ("GET", "/admin/orgs", None),
    ("GET", "/admin/orgs/tree", None),
    ("POST", "/admin/orgs", {"name": "越权", "level": "GROUP", "parentId": 1, "orgKind": "ASSIGNER"}),
    ("PUT", "/admin/orgs/1", {"name": "越权"}),
    ("DELETE", "/admin/orgs/1", None),
]

ADMIN_GET_CASES = [(method, path) for method, path, _ in ADMIN_ONLY_CASES if method == "GET"]


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_non_admin_forbidden_on_all_p5_endpoints(client):
    headers = await _login(client, "小权", "p5-matrix-u1")
    for method, path, body in ADMIN_ONLY_CASES:
        response = await client.request(method, f"/demandhub-api{path}", headers=headers, json=body)
        assert response.json()["code"] == 403, f"{method} {path} 应 403，实际 {response.json()}"


@pytest.mark.asyncio
async def test_admin_allowed_on_all_get_endpoints(client, admin_headers):
    for method, path in ADMIN_GET_CASES:
        response = await client.request(method, f"/demandhub-api{path}", headers=admin_headers)
        assert response.json()["code"] == 0, f"{method} {path} 应放行，实际 {response.json()}"
