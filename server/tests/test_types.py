"""P5 需求类型单测（蓝本 DemandTypeAdminService 口径 + /standards 表驱动联动）。

- create：type_code 大写化、^[A-Z0-9_]{2,16}$ 校验、唯一冲突、默认 DEFAULT/ACTIVE；
  state_machine_key 非空且 ≤64（蓝本：不验存在）；default_org_id 必须存在
- update：type_code 不可改，name/org/key/sort/status 可改；404/枚举校验
- /standards 联动（决策③）：表空回落 yaml；表有 ACTIVE 后以表为准、DISABLED 不出现
- API 守卫：非 ADMIN 403
"""
import pytest

from app.core.errors import BizError
from app.db.models import DemandOrg, DemandType
from app.services import type_service


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


async def _make_org(factory, org_id=950):
    async with factory() as db:
        async with db.begin():
            db.add(DemandOrg(id=org_id, name="测试承接组", level="GROUP", parent_id=100,
                             path=f"/100/{org_id}/", org_kind="ASSIGNER", status="ACTIVE"))
    return org_id


@pytest.mark.asyncio
async def test_create_normalizes_and_validates(session_factory):
    org_id = await _make_org(session_factory)
    async with session_factory() as db:
        async with db.begin():
            # 小写输入大写化
            row = await type_service.create_type(db, type_code="tech_x", type_name="测试类型",
                                                 default_org_id=org_id)
            assert row.type_code == "TECH_X" and row.state_machine_key == "DEFAULT" and row.status == "ACTIVE"
            # 非法编码逐一拒
            for bad in ("A", "含中文", "BAD-CODE", "X" * 17):
                with pytest.raises(BizError):
                    await type_service.create_type(db, type_code=bad, type_name="坏")
            # key 超长拒（不验存在：RUNTIME_ONLY 也能存）
            with pytest.raises(BizError):
                await type_service.create_type(db, type_code="K1", type_name="长key",
                                               state_machine_key="K" * 65)
            row2 = await type_service.create_type(db, type_code="K2", type_name="运行时才配",
                                                  state_machine_key="NOT_YET_EXISTS")
            assert row2.state_machine_key == "NOT_YET_EXISTS"
            # org 不存在拒
            with pytest.raises(BizError):
                await type_service.create_type(db, type_code="K3", type_name="坏org", default_org_id=999)
            # 唯一冲突
            with pytest.raises(BizError) as exc:
                await type_service.create_type(db, type_code="TECH_X", type_name="重复")
            assert "已存在" in str(exc.value)


@pytest.mark.asyncio
async def test_update_fields_and_guards(session_factory):
    org_id = await _make_org(session_factory, 951)
    async with session_factory() as db:
        async with db.begin():
            row = await type_service.create_type(db, type_code="UPD_T", type_name="原名")
            type_id = row.id
            updated = await type_service.update_type(
                db, type_id, type_name="新名", default_org_id=org_id,
                state_machine_key="CUSTOM", sort=7, status="DISABLED")
            assert updated.type_code == "UPD_T"  # 编码不可改
            assert updated.type_name == "新名" and updated.default_org_id == org_id
            assert updated.state_machine_key == "CUSTOM" and updated.sort == 7 and updated.status == "DISABLED"
            with pytest.raises(BizError):
                await type_service.update_type(db, type_id, status="BAD")
            with pytest.raises(BizError):
                await type_service.update_type(db, type_id, state_machine_key="K" * 65)
            with pytest.raises(BizError):
                await type_service.update_type(db, 999999, type_name="不存在")


@pytest.mark.asyncio
async def test_standards_table_driven(client, session_factory):
    user_headers = await _login(client, "小权", "p5-type-u1")
    # 表为空：回落 yaml 扫描（TECH/MATL/TRAIN 三类型）
    fallback = await client.get("/demandhub-api/standards", headers=user_headers)
    codes = {item["code"] for item in fallback.json()["data"]}
    assert {"TECH", "MATL", "TRAIN"} <= codes

    # 表有 ACTIVE 后：以表为准（yaml 之外的类型也出现），DISABLED 不出现
    async with session_factory() as db:
        async with db.begin():
            db.add_all([
                DemandType(type_code="TECH", type_name="科技需求（表注册名）", sort=1, status="ACTIVE"),
                DemandType(type_code="NEWBIZ", type_name="新业务", sort=2, status="ACTIVE"),
                DemandType(type_code="MATL", type_name="物料需求", sort=3, status="DISABLED"),
            ])
    driven = await client.get("/demandhub-api/standards", headers=user_headers)
    items = driven.json()["data"]
    assert [item["code"] for item in items] == ["TECH", "NEWBIZ"]
    assert items[0]["name"] == "科技需求（表注册名）"  # 表注册名覆盖 yaml 名
    assert items[0]["version"] is not None and items[1]["version"] is None  # yaml 缺失 → version None


@pytest.mark.asyncio
async def test_api_guards_and_crud(client, session_factory, admin_headers):
    user_headers = await _login(client, "小权", "p5-type-u2")
    org_id = await _make_org(session_factory, 952)

    assert (await client.get("/demandhub-api/admin/types", headers=user_headers)).json()["code"] == 403
    assert (await client.post("/demandhub-api/admin/types", headers=user_headers,
                              json={"typeCode": "X1", "typeName": "越权"})).json()["code"] == 403

    created = await client.post("/demandhub-api/admin/types", headers=admin_headers,
                                json={"typeCode": "api_t", "typeName": "接口类型", "defaultOrgId": org_id,
                                      "stateMachineKey": "DEFAULT", "sort": 9})
    assert created.json()["code"] == 0
    row = created.json()["data"]
    assert row["typeCode"] == "API_T" and row["defaultOrgId"] == org_id

    dup = await client.post("/demandhub-api/admin/types", headers=admin_headers,
                            json={"typeCode": "API_T", "typeName": "重复"})
    assert dup.json()["code"] == 409

    updated = await client.put(f"/demandhub-api/admin/types/{row['id']}", headers=admin_headers,
                               json={"status": "DISABLED", "typeName": "改名"})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["status"] == "DISABLED" and updated.json()["data"]["typeCode"] == "API_T"

    listed = await client.get("/demandhub-api/admin/types", headers=admin_headers)
    assert any(item["typeCode"] == "API_T" for item in listed.json()["data"])
