"""冒烟：OneID 二期（2026-10-18 拍板）——同名线索 suspects + 挂接记录 logs。
步骤：铸造 ADMIN 令牌（不触碰用户私有密码）
→ 建同名 PC 用户 → 渠道免登产生待归一身份 → 待归一出参 suspects 命中
→ 挂接 → 挂接记录出现 LINK 行（带过户明细、操作人）→ 渠道再进 = PC 身份（OneID 生效）→ 清理。
跑法（cwd=server，后端 8000 在跑）：python scripts_dev\\smoke_identity_phase2.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 让 scripts_dev 下的脚本能 import app

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.security import issue_token
from app.db.models import User

BASE = "http://127.0.0.1:8000/demandhub-api"
DB_URL = "mysql+asyncmy://root:local-test-only-password@127.0.0.1:3308/demandhub"
NAME = "烟测二期"          # PC 用户与渠道用户同名——suspects 只认「姓名完全一致」
ACCOUNT = "smoke-p2"
PHONE = "13922223333"
PWD = "Smoke@12345"
CH_UID = "smoke_p2_001"    # 渠道编号（渠道钥匙）


async def admin_token() -> str:
    """直接为库里的 admin 用户铸造 JWT（冒烟不需要知道其私有密码）。"""
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        row = (await conn.execute(select(User.id, User.wecom_userid, User.name, User.channel, User.role)
                                  .where(User.login_account == "admin"))).one()
    await engine.dispose()
    user = User(id=row.id, wecom_userid=row.wecom_userid, name=row.name,
                channel=row.channel, role=row.role)
    token, _ = issue_token(user)
    return token


async def ensure_whitelist():
    """冒烟渠道编号落白名单（开关开启时也能进；清理阶段删除）。"""
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text(
            "INSERT IGNORE INTO demand_channel_whitelist (channel_code, channel_user_id, display_name)"
            " VALUES ('CHUANGJIN_LS', :ch, :name)"), {"ch": CH_UID, "name": NAME})
    await engine.dispose()


async def channel_login(c: httpx.AsyncClient) -> dict:
    """渠道免登（创金零售明文直登链路）：返回响应 data（accessToken/user）。"""
    r = (await c.post(BASE + "/auth/channel-parameters",
                      json={"userid": CH_UID, "authToken": "smoke-token",
                            "userName": NAME, "department": "烟测部"})).json()
    assert r["code"] == 0, r
    return r["data"]


async def cleanup():
    """按固定键幂等清理冒烟数据（先清外键：票据/审计/身份行，再清白名单与两个用户）。"""
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM refresh_token WHERE user_id IN (SELECT id FROM dh_user WHERE "
            "login_account = :acct OR wecom_userid = :ch)"), {"acct": ACCOUNT, "ch": CH_UID})
        await conn.execute(text("DELETE FROM dh_identity_link_log WHERE channel_user_id = :ch"),
                           {"ch": CH_UID})
        await conn.execute(text("DELETE FROM dh_channel_identity WHERE channel_user_id = :ch"),
                           {"ch": CH_UID})
        await conn.execute(text("DELETE FROM demand_channel_whitelist WHERE channel_user_id = :ch"),
                           {"ch": CH_UID})
        await conn.execute(text("DELETE FROM dh_user WHERE login_account = :acct OR wecom_userid = :ch"),
                           {"acct": ACCOUNT, "ch": CH_UID})
    await engine.dispose()


async def main():
    await cleanup()            # 先清历史残留（上次失败也可能留了半成品）
    await ensure_whitelist()
    try:
        async with httpx.AsyncClient(trust_env=False) as c:
            headers = {"Authorization": "Bearer " + await admin_token()}

            # 1. 建同名 PC 用户（正式用户，suspects 的命中目标）
            r = (await c.post(BASE + "/admin/users", headers=headers,
                              json={"loginAccount": ACCOUNT, "name": NAME, "initialPassword": PWD,
                                    "role": "HANDLER", "types": ["TECH"], "phone": PHONE})).json()
            assert r["code"] == 0, r
            pc_uid = r["data"]["id"]
            print(f"[1/6] PC 用户已建（{NAME} / {ACCOUNT}）✓")

            # 2. 渠道免登 → 产生待归一身份（钥匙挂在渠道临时人名下）
            data = await channel_login(c)
            temp_uid = data["user"]["id"]
            assert temp_uid != pc_uid
            print("[2/6] 渠道免登进门（临时人身份）✓")

            # 3. 待归一列表 → suspects 命中同名 PC 用户
            r = (await c.get(BASE + "/admin/channel-identities", headers=headers,
                             params={"linked": "false", "keyword": CH_UID})).json()
            assert r["code"] == 0 and r["data"]["total"] == 1, r
            row = r["data"]["list"][0]
            identity_id = row["id"]
            suspects = row.get("suspects") or []
            assert any(s["id"] == pc_uid for s in suspects), r
            print(f"[3/6] 待归一附同名线索 suspects（{[s['loginAccount'] for s in suspects]}）✓")

            # 4. 挂接 → 身份改指 PC 用户，历史数据过户
            r = (await c.post(f"{BASE}/admin/users/{pc_uid}/channel-identities", headers=headers,
                              json={"identityId": identity_id})).json()
            assert r["code"] == 0, r
            print(f"[4/6] 挂接成功（过户：{r['data']['movedCounts']}）✓")

            # 5. 挂接记录 → 最新一条 LINK：临时人 → PC 用户，带过户明细与操作人
            r = (await c.get(BASE + "/admin/identity-link-logs", headers=headers,
                             params={"page": 1, "size": 10})).json()
            assert r["code"] == 0 and r["data"]["total"] >= 1, r
            log = r["data"]["list"][0]
            assert log["action"] == "LINK" and log["channelUserId"] == CH_UID, log
            assert log["fromUserId"] == temp_uid and log["toUserId"] == pc_uid, log
            assert log["movedCounts"] is not None and log["operatorName"], log
            print(f"[5/6] 挂接记录留痕（{log['fromUserName']} → {log['toUserName']}，操作人 {log['operatorName']}）✓")

            # 6. OneID 生效：渠道再免登 → 直接进 PC 用户身份
            data = await channel_login(c)
            assert data["user"]["id"] == pc_uid, data
            print("[6/6] 渠道再进 = PC 身份（OneID 生效）✓")
    finally:
        await cleanup()
    print("冒烟数据已清理，全部通过 ✓")


if __name__ == "__main__":
    asyncio.run(main())
