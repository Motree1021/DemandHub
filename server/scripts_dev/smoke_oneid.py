"""OneID 一期开发库冒烟：渠道进门提单 → admin 挂接 → 渠道再进=PC 身份 → 数据已归一。

冒烟数据保留在开发库（admin 后台「用户管理」可见「冒烟正式用户」及其已挂渠道身份），可手工删除。
"""
import asyncio
import json

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import issue_token
from app.db.models import Demand, User, now

BASE = "http://127.0.0.1:8000/demandhub-api"
SMOKE_UID = "smoke-oneid-001"
DB_URL = "mysql+asyncmy://root:local-test-only-password@127.0.0.1:3308/demandhub"


async def channel_entry(c: httpx.AsyncClient, name: str, admin_h: dict) -> dict:
    """渠道免登进门（开发环境 trusted_parameters 明文模式，与 ticket 模式同走身份表链路）。
    开发库白名单启用中：被 1123 拦截时自动把冒烟用户加进白名单再进门。"""
    payload = {"userid": SMOKE_UID, "authToken": "smoke-token", "userName": name,
               "department": "冒烟部"}
    r = (await c.post(f"{BASE}/auth/channel-parameters", json=payload)).json()
    if r["code"] == 1123:
        add = (await c.post(f"{BASE}/admin/channels/CHUANGJIN_LS/whitelist", headers=admin_h,
                            json={"channelUserId": SMOKE_UID, "displayName": name})).json()
        print(f"   白名单补录: code={add['code']}（已存在则忽略）")
        r = (await c.post(f"{BASE}/auth/channel-parameters", json=payload)).json()
    assert r["code"] == 0, r
    return r["data"]


async def main():
    factory = async_sessionmaker(create_async_engine(DB_URL), expire_on_commit=False)
    async with httpx.AsyncClient(trust_env=False, timeout=10) as c:
        # 0. 本地铸造 admin token（不改动 admin 密码）
        async with factory() as db:
            admin = (await db.execute(select(User).where(User.login_account == "admin"))).scalar_one()
            admin_token, _ = issue_token(admin)
        admin_h = {"Authorization": f"Bearer {admin_token}"}

        # 1. 渠道用户首次进门
        data = await channel_entry(c, "冒烟渠道用户", admin_h)
        temp = data["user"]
        print(f"1. 渠道首次进门: id={temp['id']} channel={temp['channel']} role={temp['role']}")
        assert temp["channel"] == "CHUANGJIN_LS" and temp["role"] == "REPORTER"

        # 2. 该渠道用户名下造一条历史需求（ORM 直插，聚焦 OneID 验证）
        async with factory() as db:
            async with db.begin():
                demand = Demand(title="OneID冒烟需求", demand_type_code="TECH",
                                content="挂接后应归到 PC 用户名下", urgency="NORMAL",
                                status="SUBMITTED", submitter_id=temp["id"],
                                submitter_name=temp["name"], channel="CHUANGJIN_LS",
                                client_request_id=SMOKE_UID, create_request_hash="raw",
                                submitted_at=now(), revision=0)
                db.add(demand)
                await db.flush()
                demand_id = demand.id
        print(f"2. 历史需求已造: demandId={demand_id} submitter_id={temp['id']}")

        # 3. 建 PC 用户（重复冒烟时复用）
        r = (await c.post(f"{BASE}/admin/users", headers=admin_h, json={
            "loginAccount": "smokepc", "name": "冒烟正式用户", "initialPassword": "Smoke@12345",
            "role": "HANDLER", "types": ["TECH", "MATL", "TRAIN"]})).json()
        if r["code"] == 1109 or (r["code"] != 0 and "已存在" in r.get("message", "")):
            # 重复冒烟：复用已有 PC 用户
            r = (await c.get(f"{BASE}/admin/users", headers=admin_h,
                             params={"keyword": "smokepc"})).json()
            pc = r["data"]["list"][0]
            print(f"3. PC 用户已存在（重复冒烟）: id={pc['id']}")
        else:
            assert r["code"] == 0, r
            pc = r["data"]
            print(f"3. 建 PC 用户: id={pc['id']} account={pc['loginAccount']}")

        # 4. 查未归属身份并挂接
        r = (await c.get(f"{BASE}/admin/channel-identities",
                         params={"keyword": SMOKE_UID}, headers=admin_h)).json()
        assert r["code"] == 0, r
        candidates = [i for i in r["data"]["list"] if i["channelUserId"] == SMOKE_UID]
        if candidates:
            identity = candidates[0]
            print(f"4. 未归属身份: id={identity['id']} 临时账号={identity['ownerName']}")
            r = (await c.post(f"{BASE}/admin/users/{pc['id']}/channel-identities",
                              json={"identityId": identity["id"]}, headers=admin_h)).json()
            assert r["code"] == 0, r
            print(f"5. 挂接完成: 过户={json.dumps(r['data']['movedCounts'], ensure_ascii=False)}")
        else:
            print("4/5. 身份已挂接过（重复冒烟），跳过")

        # 6. 渠道再进门 → 应是 PC 用户身份
        data = await channel_entry(c, "冒烟渠道用户改名", admin_h)
        landed = data["user"]
        print(f"6. 渠道再进门: id={landed['id']} name={landed['name']} role={landed['role']}")
        assert landed["id"] == pc["id"], "OneID 未生效！"
        assert landed["name"] == "冒烟正式用户"  # PC 姓名不被渠道快照覆盖

        # 7. 历史需求已过户到 PC 用户名下
        async with factory() as db:
            demand = await db.get(Demand, demand_id)
            assert demand.submitter_id == pc["id"], f"需求未归一: {demand.submitter_id}"
            print(f"7. 需求已归一: demandId={demand_id} submitter_id={demand.submitter_id} "
                  f"（快照名仍={demand.submitter_name}）")

        # 8. 已挂列表出参（admin 弹窗数据源）
        r = (await c.get(f"{BASE}/admin/users/{pc['id']}/channel-identities", headers=admin_h)).json()
        assert r["data"] and r["data"][0]["channelUserId"] == SMOKE_UID, r
        print(f"8. PC 用户已挂身份: {json.dumps(r['data'], ensure_ascii=False)}")
        print("冒烟全部通过 ✓")


if __name__ == "__main__":
    asyncio.run(main())
