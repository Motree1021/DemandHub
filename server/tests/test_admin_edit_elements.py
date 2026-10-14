"""管理端改要素（PATCH /demand/{id}/elements）：编辑落库、质量重算、留痕、乐观锁、终态拒绝。"""

from uuid import uuid4

from app.core.errors import ErrorCode

BASE = "/demandhub-api"

TECH_FORM = dict(
    title="换logo", demandTypeCode="TECH",
    content="把系统logo换成公司新版logo，橙蓝色为主", urgency="NORMAL",
    elements={"A": {"techSubtype": "OPS_OPT"},
              "C": {"userRole": "客户经理", "userGoal": "登录时看到新logo形象",
                    "useScenario": "每次登录系统时客户经理看到新logo", "painPoint": "旧logo与公司风格不一致"},
              "D": {"functionDescription": "替换系统logo为橙蓝风格", "inputOutput": "输入新logo图片输出展示页面",
                    "acceptanceCriteria": "名称显示为话术生成与分发系统，logo为橙蓝公司风格"}})


async def create_submitted(client, headers) -> dict:
    resp = await client.post(BASE + "/demand", headers=headers, json={"clientRequestId": str(uuid4()), **TECH_FORM})
    assert resp.json()["code"] == 0, resp.text
    draft = resp.json()["data"]
    submitted = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=headers,
                                  json={"expectedRevision": draft["revision"]})
    assert submitted.json()["code"] == 0, submitted.text
    return submitted.json()["data"]


async def test_edit_elements_happy_path(client, auth_headers):
    """提交后补填 B 区要素：落库 + revision+1 + 质量重算（businessGoal 由缺失转到位）+ 留痕。"""
    demand = await create_submitted(client, auth_headers)
    quality_before = {q["key"]: q["status"] for q in demand["quality"]}
    assert quality_before["businessGoal"] == "MISSING"

    resp = await client.patch(f"{BASE}/demand/{demand['id']}/elements", headers=auth_headers,
                              json={"expectedRevision": demand["revision"],
                                    "elements": {"B": {"businessGoal": "把晨会数据准备时间从2小时缩短到10分钟"}}})
    assert resp.json()["code"] == 0, resp.text
    data = resp.json()["data"]
    assert data["demand"]["revision"] == demand["revision"] + 1
    assert data["demand"]["elements"]["B"]["businessGoal"] == "把晨会数据准备时间从2小时缩短到10分钟"
    quality_after = {q["key"]: q["status"] for q in data["quality"]}
    assert quality_after["businessGoal"] == "OK"
    assert any(log["fieldKey"] == "elements.B.businessGoal" and "缩短到10分钟" in (log["newValue"] or "")
               for log in data["demand"]["changeLogs"])


async def test_edit_elements_revision_conflict(client, auth_headers):
    demand = await create_submitted(client, auth_headers)
    resp = await client.patch(f"{BASE}/demand/{demand['id']}/elements", headers=auth_headers,
                              json={"expectedRevision": demand["revision"] + 9,
                                    "elements": {"B": {"businessGoal": "x"}}})
    assert resp.json()["code"] == ErrorCode.CONFLICT.code


async def test_edit_elements_terminal_rejected(client, auth_headers, db):
    from app.db.models import Demand
    demand = await create_submitted(client, auth_headers)
    row = await db.get(Demand, demand["id"])
    row.status = "DONE"
    await db.commit()
    resp = await client.patch(f"{BASE}/demand/{demand['id']}/elements", headers=auth_headers,
                              json={"expectedRevision": demand["revision"],
                                    "elements": {"B": {"businessGoal": "x"}}})
    assert resp.json()["code"] == ErrorCode.BIZ_ERROR.code


async def test_edit_elements_not_found(client, auth_headers):
    resp = await client.patch(f"{BASE}/demand/999999/elements", headers=auth_headers,
                              json={"expectedRevision": 0, "elements": {"B": {"businessGoal": "x"}}})
    assert resp.json()["code"] == ErrorCode.DEMAND_NOT_FOUND.code
