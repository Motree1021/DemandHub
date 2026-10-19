"""P5 渠道管理单测（蓝本 ChannelAdminService，决策②裁剪版：只做登记/启停）。

- list：渠道无新增/删除接口（SQL 种子注册）；config_json 预留列 secret 脱敏 "***"
- update_status：ACTIVE/DISABLED 枚举校验、404
- dept-unmapped：校准清单只读 + 删行（记录 upsert 属登录链路本期不动）；channelCode 过滤、404
- API 守卫：非 ADMIN 403
"""
import pytest

from app.core.errors import BizError
from app.db.models import ChannelDeptUnmapped, DemandChannel
from app.services import channel_service as service


async def _login(client, name, wecom_userid):
    response = await client.post("/demandhub-api/auth/dev-login",
                                 json={"name": name, "wecomUserid": wecom_userid})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["accessToken"]}


@pytest.mark.asyncio
async def test_list_and_secret_masked(session_factory):
    async with session_factory() as db:
        async with db.begin():
            db.add(DemandChannel(channel_code="WEB", channel_name="网页", status="ACTIVE"))
            db.add(DemandChannel(channel_code="CHUANGJIN_LS", channel_name="创金零售",
                                 status="ACTIVE", app_id="cjls",
                                 config_json={"appSecret": "s3cr3t", "ssoVerifyBaseUrl": "https://x"}))
            rows = await service.list_channels(db)
    assert [r["channelCode"] for r in rows] == ["WEB", "CHUANGJIN_LS"]
    config = rows[1]["configJson"]
    assert config["appSecret"] == "***"  # secret 脱敏
    assert config["ssoVerifyBaseUrl"] == "https://x"  # 非 secret 透传
    assert rows[0]["configJson"] is None and rows[1]["appId"] == "cjls"


@pytest.mark.asyncio
async def test_update_status_guards(session_factory):
    async with session_factory() as db:
        async with db.begin():
            db.add(DemandChannel(channel_code="WECOM", channel_name="企微", status="DISABLED"))
            channel_id = (await service.list_channels(db))[0]["id"]
            row = await service.update_status(db, channel_id, status="ACTIVE")
            assert row.status == "ACTIVE"
            with pytest.raises(BizError):
                await service.update_status(db, channel_id, status="BAD")
            with pytest.raises(BizError):
                await service.update_status(db, 999999, status="ACTIVE")


@pytest.mark.asyncio
async def test_unmapped_list_filter_and_delete(session_factory):
    async with session_factory() as db:
        async with db.begin():
            db.add_all([
                ChannelDeptUnmapped(channel_code="CHUANGJIN_LS", dept_id="D1",
                                    dept_name="渠道一部", hit_count=3),
                ChannelDeptUnmapped(channel_code="CHUANGJIN_LS", dept_id="D2"),
                ChannelDeptUnmapped(channel_code="WECOM", dept_id="D9"),
            ])
            all_rows = await service.list_unmapped(db)
            assert len(all_rows) == 3
            cj = await service.list_unmapped(db, "CHUANGJIN_LS")
            assert {r["deptId"] for r in cj} == {"D1", "D2"}
            target = next(r for r in all_rows if r["deptId"] == "D9")
            assert target["hitCount"] == 1
            await service.delete_unmapped(db, target["id"])
            assert len(await service.list_unmapped(db)) == 2
            with pytest.raises(BizError):
                await service.delete_unmapped(db, target["id"])  # 已删 404


@pytest.mark.asyncio
async def test_api_guards_and_crud(client, session_factory, admin_headers):
    user_headers = await _login(client, "小权", "p5-ch-u1")
    async with session_factory() as db:
        async with db.begin():
            db.add(DemandChannel(channel_code="WEB", channel_name="网页", status="ACTIVE"))
            db.add(ChannelDeptUnmapped(channel_code="WEB", dept_id="D1"))

    assert (await client.get("/demandhub-api/admin/channels", headers=user_headers)).json()["code"] == 403
    listed = await client.get("/demandhub-api/admin/channels", headers=admin_headers)
    assert listed.json()["code"] == 0
    row = next(r for r in listed.json()["data"] if r["channelCode"] == "WEB")

    bad = await client.put(f"/demandhub-api/admin/channels/{row['id']}/status",
                           headers=admin_headers, json={"status": "BAD"})
    assert bad.json()["code"] != 0

    disabled = await client.put(f"/demandhub-api/admin/channels/{row['id']}/status",
                                headers=admin_headers, json={"status": "DISABLED"})
    assert disabled.json()["code"] == 0 and disabled.json()["data"]["status"] == "DISABLED"

    unmapped = await client.get("/demandhub-api/admin/channels/dept-unmapped?channelCode=WEB",
                                headers=admin_headers)
    records = unmapped.json()["data"]
    assert len(records) == 1 and records[0]["deptId"] == "D1"

    removed = await client.delete(f"/demandhub-api/admin/channels/dept-unmapped/{records[0]['id']}",
                                  headers=admin_headers)
    assert removed.json()["code"] == 0
    assert (await client.get("/demandhub-api/admin/channels/dept-unmapped",
                             headers=admin_headers)).json()["data"] == []
