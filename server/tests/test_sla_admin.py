"""P5 SLA 配置管理单测（蓝本 SlaConfigAdminService 口径）。

- create：uk(demand_type_code, status) 冲突 409；warn/max 正整数且 warn < max；
  status 仅允许主状态（ON_HOLD 叠加态拒）
- update：组合不可改，warn/max/enabled/remark 可改；合并校验（只改 max 也要满足 warn < max）；404
- delete：蓝本有 DELETE（区别于字典）；404
- API 守卫：非 ADMIN 403
"""
import pytest

from app.core.errors import BizError
from app.services import sla_admin_service as service


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_create_validates_and_unique(session_factory):
    async with session_factory() as db:
        async with db.begin():
            row = await service.create_config(db, demand_type_code="TECH", status="SUBMITTED",
                                              warn_minutes=60, max_minutes=120, remark="r")
            assert row.enabled is True
            # 组合冲突
            with pytest.raises(BizError) as exc:
                await service.create_config(db, demand_type_code="TECH", status="SUBMITTED",
                                            warn_minutes=10, max_minutes=20)
            assert "已存在" in str(exc.value)
            # ON_HOLD 叠加态拒
            with pytest.raises(BizError):
                await service.create_config(db, demand_type_code="TECH", status="ON_HOLD",
                                            warn_minutes=10, max_minutes=20)
            # 非法状态拒
            with pytest.raises(BizError):
                await service.create_config(db, demand_type_code="TECH", status="NOWHERE",
                                            warn_minutes=10, max_minutes=20)
            # 非正数拒
            with pytest.raises(BizError):
                await service.create_config(db, demand_type_code="TECH", status="TRIAGE",
                                            warn_minutes=0, max_minutes=20)
            # warn >= max 拒（黄档必须先于红档）
            with pytest.raises(BizError):
                await service.create_config(db, demand_type_code="TECH", status="TRIAGE",
                                            warn_minutes=120, max_minutes=120)


@pytest.mark.asyncio
async def test_update_merge_check_and_delete(session_factory):
    async with session_factory() as db:
        async with db.begin():
            row = await service.create_config(db, demand_type_code="MATL", status="TRIAGE",
                                              warn_minutes=100, max_minutes=200)
            config_id = row.id
            # 只改 max：与已有 warn=100 合并校验
            with pytest.raises(BizError):
                await service.update_config(db, config_id, max_minutes=100)
            updated = await service.update_config(db, config_id, max_minutes=300,
                                                  enabled=False, remark="停用观察")
            assert updated.warn_minutes == 100 and updated.max_minutes == 300
            assert updated.enabled is False and updated.remark == "停用观察"
            assert updated.demand_type_code == "MATL" and updated.status == "TRIAGE"  # 组合不可改
            with pytest.raises(BizError):
                await service.update_config(db, 999999, warn_minutes=1)
            await service.delete_config(db, config_id)
            with pytest.raises(BizError):
                await service.delete_config(db, config_id)  # 已删 404
            # 删除后同组合可重建
            await service.create_config(db, demand_type_code="MATL", status="TRIAGE",
                                        warn_minutes=10, max_minutes=20)


@pytest.mark.asyncio
async def test_list_filter(session_factory):
    async with session_factory() as db:
        async with db.begin():
            await service.create_config(db, demand_type_code="TECH", status="SUBMITTED",
                                        warn_minutes=10, max_minutes=20)
            await service.create_config(db, demand_type_code="TECH", status="TRIAGE",
                                        warn_minutes=10, max_minutes=20)
            await service.create_config(db, demand_type_code="MATL", status="SUBMITTED",
                                        warn_minutes=10, max_minutes=20)
            all_rows = await service.list_configs(db)
            assert len(all_rows) == 3
            tech_only = await service.list_configs(db, "TECH")
            assert [r["status"] for r in tech_only] == ["SUBMITTED", "TRIAGE"]


@pytest.mark.asyncio
async def test_api_guards_and_crud(client):
    admin_headers = await _login(client, "超管", "mvp-admin")
    user_headers = await _login(client, "小权", "p5-sla-u1")

    assert (await client.get("/demandhub-api/admin/sla-configs", headers=user_headers)).json()["code"] == 403
    assert (await client.post("/demandhub-api/admin/sla-configs", headers=user_headers,
                              json={"demandTypeCode": "TECH", "status": "SUBMITTED",
                                    "warnMinutes": 10, "maxMinutes": 20})).json()["code"] == 403

    created = await client.post("/demandhub-api/admin/sla-configs", headers=admin_headers,
                                json={"demandTypeCode": "TRAIN", "status": "SUBMITTED",
                                      "warnMinutes": 1440, "maxMinutes": 2880, "remark": "受理时限"})
    assert created.json()["code"] == 0
    row = created.json()["data"]
    assert row["demandTypeCode"] == "TRAIN" and row["enabled"] is True

    dup = await client.post("/demandhub-api/admin/sla-configs", headers=admin_headers,
                            json={"demandTypeCode": "TRAIN", "status": "SUBMITTED",
                                  "warnMinutes": 1, "maxMinutes": 2})
    assert dup.json()["code"] == 409

    bad = await client.post("/demandhub-api/admin/sla-configs", headers=admin_headers,
                            json={"demandTypeCode": "TRAIN", "status": "TRIAGE",
                                  "warnMinutes": 200, "maxMinutes": 100})
    assert bad.json()["code"] != 0 and "小于" in bad.json()["message"]

    updated = await client.put(f"/demandhub-api/admin/sla-configs/{row['id']}",
                               headers=admin_headers, json={"enabled": False, "warnMinutes": 720})
    assert updated.json()["code"] == 0
    assert updated.json()["data"]["enabled"] is False and updated.json()["data"]["warnMinutes"] == 720

    listed = await client.get("/demandhub-api/admin/sla-configs?demandTypeCode=TRAIN",
                              headers=admin_headers)
    assert [item["id"] for item in listed.json()["data"]] == [row["id"]]

    removed = await client.delete(f"/demandhub-api/admin/sla-configs/{row['id']}",
                                  headers=admin_headers)
    assert removed.json()["code"] == 0
    assert (await client.delete(f"/demandhub-api/admin/sla-configs/{row['id']}",
                                headers=admin_headers)).json()["code"] == 404
