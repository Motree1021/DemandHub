"""P5 状态机配置管理单测（蓝本 StateMachineConfigAdminService 口径）。

- validate_rules 聚合校验：所有错误一次性报全（区别于加载侧首错即抛）
- create：key 唯一 409、保存即热刷（find_rule 不重启立即命中新规则）
- update：config_key 不可改；config_json 变更 version+1，不变则不加；状态枚举/404
- /default-json：内置兜底规则 pretty JSON，可直接用于新建
- API 守卫：非 ADMIN 403
"""
import json

import pytest

from app.core.errors import BizError
from app.core.statemachine import engine
from app.services import statemachine_service as service

VALID_JSON = json.dumps({"rules": [
    {"from": "DRAFT", "event": "SUBMIT", "to": "SUBMITTED", "roles": [], "remark": "提交"},
]}, ensure_ascii=False)


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_validate_rules_aggregates_errors():
    # 合法
    assert engine.validate_rules(VALID_JSON) == []
    # JSON 解析失败
    assert engine.validate_rules("{oops") == ["JSON 解析失败: Expecting property name enclosed in double quotes"]
    # rules 非空数组
    assert engine.validate_rules("{}") == ["rules 必须为非空数组"]
    assert engine.validate_rules('{"rules": []}') == ["rules 必须为非空数组"]
    # 聚合：多条错误一次性全报
    errors = engine.validate_rules(json.dumps({"rules": [
        {"from": "BAD", "event": "", "to": "NOWHERE", "roles": ["ROOT"]},
        "not-a-dict",
        {"from": "DRAFT", "event": "FLY", "to": None, "roles": ["HANDLER"]},
    ]}))
    assert any("第1条：源状态[BAD]非法" in e for e in errors)
    assert any("第1条：事件必填" in e for e in errors)
    assert any("第1条：目标状态[NOWHERE]非法" in e for e in errors)
    assert any("第1条：角色仅允许" in e for e in errors)
    assert any("第2条：须为对象" in e for e in errors)
    assert any("第3条：事件[FLY]非法" in e for e in errors)


@pytest.mark.asyncio
async def test_create_unique_and_hot_reload(session_factory):
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError):  # 非法 JSON 拒存
                await service.create_config(db, config_key="T_BAD", config_name="坏",
                                            config_json='{"rules": []}')
            row = await service.create_config(db, config_key="T_HOT", config_name="热刷",
                                              config_json=VALID_JSON, remark="r")
            assert row.status == "ACTIVE" and row.version == 1
            with pytest.raises(BizError) as exc:  # key 唯一
                await service.create_config(db, config_key="T_HOT", config_name="重复",
                                            config_json=VALID_JSON)
            assert "已存在" in str(exc.value)
    # 保存即热刷：不重启、不调 /reload，引擎立即命中新规则
    rule = engine.find_rule("DRAFT", "SUBMIT", "T_HOT")
    assert rule is not None and rule.to == "SUBMITTED"
    assert engine.find_rule("DRAFT", "SUBMIT", "T_HOT").remark == "提交"


@pytest.mark.asyncio
async def test_update_version_and_hot_reload(session_factory):
    new_json = json.dumps({"rules": [
        {"from": "DRAFT", "event": "SUBMIT", "to": "TRIAGE", "roles": ["MANAGER"], "remark": "直达分派"},
    ]}, ensure_ascii=False)
    async with session_factory() as db:
        async with db.begin():
            row = await service.create_config(db, config_key="T_VER", config_name="版本",
                                              config_json=VALID_JSON)
            config_id = row.id
            # 只改名：version 不动
            renamed = await service.update_config(db, config_id, config_name="改名")
            assert renamed.version == 1 and renamed.config_key == "T_VER"  # key 不可改
            # 改 JSON：version+1 且热刷
            updated = await service.update_config(db, config_id, config_json=new_json,
                                                  status="ACTIVE", remark="新")
            assert updated.version == 2 and updated.remark == "新"
            with pytest.raises(BizError):
                await service.update_config(db, config_id, status="BAD")
            with pytest.raises(BizError):
                await service.update_config(db, 999999, config_name="不存在")
    # 热刷断言：DRAFT-SUBMIT 现在直达 TRIAGE 且仅 MANAGER
    rule = engine.find_rule("DRAFT", "SUBMIT", "T_VER")
    assert rule.to == "TRIAGE" and rule.roles == frozenset({"MANAGER"})


@pytest.mark.asyncio
async def test_default_json_is_valid_and_parseable():
    payload = json.loads(service.default_json())
    assert len(payload["rules"]) == len(engine.DEFAULT_RULES)
    assert engine.validate_rules(service.default_json()) == []  # 默认配置必须能过聚合校验


@pytest.mark.asyncio
async def test_api_guards_and_crud(client):
    admin_headers = await _login(client, "超管", "mvp-admin")
    user_headers = await _login(client, "小权", "p5-sm-u1")

    assert (await client.get("/demandhub-api/admin/state-machines", headers=user_headers)).json()["code"] == 403
    assert (await client.post("/demandhub-api/admin/state-machines", headers=user_headers,
                              json={"configKey": "T_API", "configName": "越权",
                                    "configJson": VALID_JSON})).json()["code"] == 403

    # 默认 JSON 可直接新建
    default = await client.get("/demandhub-api/admin/state-machines/default-json", headers=admin_headers)
    assert default.json()["code"] == 0
    default_config = default.json()["data"]["configJson"]
    assert json.loads(default_config)["rules"]

    created = await client.post("/demandhub-api/admin/state-machines", headers=admin_headers,
                                json={"configKey": "T_API", "configName": "接口机",
                                      "configJson": default_config, "remark": "r"})
    assert created.json()["code"] == 0
    row = created.json()["data"]
    assert row["configKey"] == "T_API" and row["version"] == 1 and row["status"] == "ACTIVE"

    dup = await client.post("/demandhub-api/admin/state-machines", headers=admin_headers,
                            json={"configKey": "T_API", "configName": "重复", "configJson": default_config})
    assert dup.json()["code"] == 409

    bad = await client.post("/demandhub-api/admin/state-machines", headers=admin_headers,
                            json={"configKey": "T_BAD2", "configName": "坏",
                                  "configJson": '{"rules": [{"from": "X", "event": "SUBMIT", "to": "DONE"}]}'})
    assert bad.json()["code"] != 0 and "第1条" in bad.json()["message"]

    updated = await client.put(f"/demandhub-api/admin/state-machines/{row['id']}",
                               headers=admin_headers,
                               json={"configName": "改名", "status": "DISABLED"})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["status"] == "DISABLED" and updated.json()["data"]["version"] == 1

    listed = await client.get("/demandhub-api/admin/state-machines", headers=admin_headers)
    assert any(item["configKey"] == "T_API" for item in listed.json()["data"])

    # 手动重载仍可用
    reloaded = await client.post("/demandhub-api/admin/state-machines/reload", headers=admin_headers)
    assert reloaded.json()["code"] == 0
