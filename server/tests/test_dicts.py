"""P5 业务字典单测（蓝本 SysDictAdminService 口径）。

- create：三字段非空（API 层 Field 校验）、dict_type+item_code 唯一冲突、默认 ACTIVE/sort 0
- update：仅 itemName/sort/status 生效（编码不可改）、status 枚举校验、不存在 404
- 列表：dictType+sort+id 升序；types 分组去重排序；登录查询仅 ACTIVE
- API 守卫：非 ADMIN 403（body 业务码），ADMIN 放行
"""
import pytest

from app.core.errors import BizError
from app.services import dict_service


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_create_and_conflict(session_factory):
    async with session_factory() as db:
        async with db.begin():
            row = await dict_service.create_dict(
                db, dict_type="TEST_GROUP", item_code="A", item_name="甲")
            assert row.status == "ACTIVE" and row.sort == 0 and row.id > 0
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError) as exc:
                await dict_service.create_dict(db, dict_type="TEST_GROUP", item_code="A", item_name="甲二")
            assert "字典项已存在" in str(exc.value)


@pytest.mark.asyncio
async def test_update_only_name_sort_status(session_factory):
    async with session_factory() as db:
        async with db.begin():
            row = await dict_service.create_dict(
                db, dict_type="TEST_UPD", item_code="B", item_name="原名", sort=1)
            dict_id = row.id
    async with session_factory() as db:
        async with db.begin():
            updated = await dict_service.update_dict(db, dict_id, item_name="新名", sort=5, status="DISABLED")
            assert updated.item_name == "新名" and updated.sort == 5 and updated.status == "DISABLED"
            # 编码与分组不可改（蓝本口径：历史数据按编码关联）
            assert updated.dict_type == "TEST_UPD" and updated.item_code == "B"
    async with session_factory() as db:
        async with db.begin():
            with pytest.raises(BizError):
                await dict_service.update_dict(db, dict_id, status="BAD")
            with pytest.raises(BizError):
                await dict_service.update_dict(db, 999999, item_name="不存在")


@pytest.mark.asyncio
async def test_list_order_and_active_filter(session_factory):
    async with session_factory() as db:
        async with db.begin():
            await dict_service.create_dict(db, dict_type="TEST_SORT", item_code="S2", item_name="第二", sort=2)
            await dict_service.create_dict(db, dict_type="TEST_SORT", item_code="S1", item_name="第一", sort=1)
            await dict_service.create_dict(db, dict_type="TEST_SORT", item_code="S0", item_name="停用", sort=0)
            rows = await dict_service.list_dicts(db, dict_type="TEST_SORT")
            assert [r["itemCode"] for r in rows] == ["S0", "S1", "S2"]
            await dict_service.update_dict(db, rows[0]["id"], status="DISABLED")
    async with session_factory() as db:
        active = await dict_service.list_active(db, dict_type="TEST_SORT")
        assert [r["itemCode"] for r in active] == ["S1", "S2"]
        types = await dict_service.list_types(db)
        assert "TEST_SORT" in types and types == sorted(types)


@pytest.mark.asyncio
async def test_api_guards_and_crud(client, session_factory, admin_headers):
    user_headers = await _login(client, "小权", "p5-dict-u1")

    # 非 ADMIN 全 403（body 业务码）
    assert (await client.get("/demandhub-api/admin/dicts", headers=user_headers)).json()["code"] == 403
    assert (await client.post("/demandhub-api/admin/dicts", headers=user_headers,
                              json={"dictType": "G", "itemCode": "C", "itemName": "N"})).json()["code"] == 403

    created = await client.post("/demandhub-api/admin/dicts", headers=admin_headers,
                                json={"dictType": "API_G", "itemCode": "X1", "itemName": "接口项", "sort": 3})
    assert created.json()["code"] == 0
    row = created.json()["data"]
    assert row["dictType"] == "API_G" and row["status"] == "ACTIVE" and row["sort"] == 3

    # 唯一冲突 → 409 业务码
    dup = await client.post("/demandhub-api/admin/dicts", headers=admin_headers,
                            json={"dictType": "API_G", "itemCode": "X1", "itemName": "重复"})
    assert dup.json()["code"] == 409

    updated = await client.put(f"/demandhub-api/admin/dicts/{row['id']}", headers=admin_headers,
                               json={"status": "DISABLED", "itemName": "改名"})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["status"] == "DISABLED" and updated.json()["data"]["itemCode"] == "X1"

    listed = await client.get("/demandhub-api/admin/dicts?dictType=API_G", headers=admin_headers)
    assert [r["itemCode"] for r in listed.json()["data"]] == ["X1"]
    types = await client.get("/demandhub-api/admin/dicts/types", headers=admin_headers)
    assert "API_G" in types.json()["data"]

    # 登录用户查询：仅 ACTIVE（已停用的 X1 不出现，新加的 X2 可见）
    await client.post("/demandhub-api/admin/dicts", headers=admin_headers,
                      json={"dictType": "API_G", "itemCode": "X2", "itemName": "启用项"})
    active = await client.get("/demandhub-api/dicts?dictType=API_G", headers=user_headers)
    assert active.json()["code"] == 0
    assert [r["itemCode"] for r in active.json()["data"]] == ["X2"]
