"""冒烟：手机号必填/判重/可登录（2026-10-18 需求）。
步骤：铸造 ADMIN 令牌（不触碰用户私有密码；账密链路本身由手机号登录步骤覆盖验证）
→ 缺手机号 400 → 建带手机号用户 → 手机号登录/改密 → 同手机号再建(1129) → 清理。
跑法（cwd=server，后端 8000 在跑）：python scripts_dev\\smoke_phone_login.py
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
PHONE = "13911112222"
ACCOUNT = "smoke-phone"
PWD = "Smoke@12345"
DB_URL = "mysql+asyncmy://root:local-test-only-password@127.0.0.1:3308/demandhub"


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


async def main():
    async with httpx.AsyncClient(trust_env=False) as c:
        headers = {"Authorization": "Bearer " + await admin_token()}

        # 2. 缺手机号 → 400（必填）
        r = (await c.post(BASE + "/admin/users", headers=headers,
                          json={"loginAccount": ACCOUNT, "name": "冒烟手机", "initialPassword": PWD,
                                "role": "HANDLER", "types": ["TECH"]})).json()
        assert r["code"] == 400, r
        print("[1/5] 缺手机号被拒 400 ✓")

        # 3. 建带手机号用户
        r = (await c.post(BASE + "/admin/users", headers=headers,
                          json={"loginAccount": ACCOUNT, "name": "冒烟手机", "initialPassword": PWD,
                                "role": "HANDLER", "types": ["TECH"], "phone": PHONE,
                                "email": "smoke.phone@example.com"})).json()
        assert r["code"] == 0, r
        assert r["data"]["phone"] == "139****2222"  # 出参脱敏
        uid = r["data"]["id"]
        print(f"[2/5] 创建成功（脱敏出参 {r['data']['phone']}）✓")

        # 4. 手机号登录 → 同一个人（首登需改密：先改密再验登录）
        r = (await c.post(BASE + "/auth/login", json={"loginAccount": PHONE, "password": PWD})).json()
        assert r["code"] == 0 and r["data"]["user"]["id"] == uid, r
        print("[3/5] 手机号登录命中同一用户 ✓")
        # 改掉初始密码（消除 must_change_pwd，便于用户日后用手机号登录体验）
        r = (await c.post(BASE + "/auth/change-password", headers={"Authorization": "Bearer " + r["data"]["accessToken"]},
                          json={"oldPassword": PWD, "newPassword": "Smoke@67890"})).json()
        assert r["code"] == 0, r
        r = (await c.post(BASE + "/auth/login", json={"loginAccount": PHONE, "password": "Smoke@67890"})).json()
        assert r["code"] == 0 and not r["data"]["mustChangePwd"], r
        print("[4/5] 改密后手机号再登录 ✓")

        # 5. 同手机号再建 → 1129
        r = (await c.post(BASE + "/admin/users", headers=headers,
                          json={"loginAccount": "smoke-phone-2", "name": "撞手机", "initialPassword": PWD,
                                "role": "HANDLER", "types": ["TECH"], "phone": PHONE})).json()
        assert r["code"] == 1129, r
        print(f"[5/5] 手机号判重 1129（{r['message']}）✓")

    # 清理冒烟数据（refresh_token 外键级联手动清）
    engine = create_async_engine("mysql+asyncmy://root:local-test-only-password@127.0.0.1:3308/demandhub")
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM refresh_token WHERE user_id IN "
                                "(SELECT id FROM dh_user WHERE login_account LIKE 'smoke-phone%')"))
        await conn.execute(text("DELETE FROM dh_user WHERE login_account LIKE 'smoke-phone%'"))
    await engine.dispose()
    print("冒烟数据已清理，全部通过 ✓")


if __name__ == "__main__":
    asyncio.run(main())
