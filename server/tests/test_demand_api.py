from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook

BASE = "/demandhub-api"


async def create(client, headers, **fields):
    response = await client.post(BASE + "/demand", headers=headers, json={"clientRequestId": str(uuid4()), **fields})
    assert response.json()["code"] == 0, response.text
    return response.json()["data"]


async def test_draft_can_be_closed(client, auth_headers):
    # 草稿允许撤销（DRAFT → CLOSED）；已撤销不可重复流转
    draft = await create(client, auth_headers, title="要撤销的草稿")
    closed = await client.post(f"{BASE}/demand/{draft['id']}/close", headers=auth_headers, json={"reason": "提报人撤销草稿"})
    assert closed.json()["code"] == 0, closed.text
    assert closed.json()["data"]["status"] == "CLOSED" and closed.json()["data"]["closeReason"] == "提报人撤销草稿"
    again = await client.post(f"{BASE}/demand/{draft['id']}/close", headers=auth_headers, json={"reason": "重复撤销"})
    assert again.json()["code"] == 1001


async def test_blank_string_enums_accepted_as_none(client, auth_headers):
    # H5 newForm 以空字符串表示空值（urgency: ''）；Literal 字段须在 schema 层归一为 None 而非 422
    draft = await create(client, auth_headers, urgency="", demandTypeCode="")
    assert draft["urgency"] is None and draft["demandTypeCode"] is None
    updated = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "urgency": ""})
    assert updated.json()["code"] == 0, updated.text
    assert updated.json()["data"]["urgency"] is None


async def test_incomplete_draft_full_lifecycle(client, auth_headers):
    draft = await create(client, auth_headers)
    assert draft["demandNo"] is None and draft["demandTypeCode"] is None
    response = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=auth_headers, json={"expectedRevision": 0})
    assert response.json()["code"] == 400
    response = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "title": "持仓数据报表", "demandTypeCode": "TECH", "content": "每天晨会前需要自动整理渠道持仓数据，替代手工Excel统计", "urgency": "NORMAL",
        "elements": {"A": {"techSubtype": "DATA_RPT"},
                     "C": {"userRole": "客户经理", "userGoal": "晨会前快速查看各渠道持仓汇总", "useScenario": "每周客户经理查询各渠道持仓并整理晨会材料", "painPoint": "手工汇总20多个机构持仓每次近1小时", "unknown": "filtered"},
                     "D": {"functionDescription": "按机构汇总前一交易日持仓并支持导出", "inputOutput": "输入交易流水输出持仓报表", "acceptanceCriteria": "连续7天对账误差为0"}}})
    assert response.json()["code"] == 0, response.text
    updated = response.json()["data"]
    assert updated["fieldSources"]["title"] == "user" and "unknown" not in (updated["elements"].get("C") or {})
    response = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=auth_headers, json={"expectedRevision": updated["revision"]})
    assert response.json()["code"] == 0, response.text
    submitted = response.json()["data"]
    assert submitted["demandNo"].startswith("TECH-") and submitted["quality"] and submitted["standardVersionId"]
    replay = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=auth_headers, json={"expectedRevision": 0})
    assert replay.json()["data"]["demandNo"] == submitted["demandNo"]
    detail = await client.get(f"{BASE}/demand/{draft['id']}", headers=auth_headers)
    assert detail.json()["data"]["standard"]["name"] == "科技需求"
    markdown = await client.get(f"{BASE}/demand/{draft['id']}/export.md", headers=auth_headers)
    assert "持仓数据报表" in markdown.text and "误差为0" in markdown.text
    mine = await client.get(BASE + "/demand/my", headers=auth_headers)
    assert mine.json()["data"]["total"] == 1
    closed = await client.post(f"{BASE}/demand/{draft['id']}/close", headers=auth_headers, json={"reason": "业务调整"})
    assert closed.json()["data"]["status"] == "CLOSED"


async def test_create_replay_and_conflict(client, auth_headers):
    payload = {"clientRequestId": "stable-id", "title": "草稿标题"}
    a = await client.post(BASE + "/demand", headers=auth_headers, json=payload)
    b = await client.post(BASE + "/demand", headers=auth_headers, json=payload)
    assert a.json()["data"]["id"] == b.json()["data"]["id"]
    changed = await client.post(BASE + "/demand", headers=auth_headers, json={**payload, "title": "另一标题"})
    assert changed.json()["code"] == 409


async def test_revision_owner_and_admin_export(client, auth_headers):
    draft = await create(client, auth_headers, demandTypeCode="TECH", title="=FORMULA", content="业务描述", elements={"C": {"useScenario": "=SUM(1,2)"}})
    a = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "title": "手动修改"})
    assert a.json()["code"] == 0
    old = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "title": "覆盖"})
    assert old.json()["code"] == 409
    login = await client.post(BASE + "/auth/dev-login", json={"name": "其他", "wecomUserid": "other"})
    other = {"Authorization": "Bearer " + login.json()["data"]["accessToken"]}
    assert (await client.get(f"{BASE}/demand/{draft['id']}", headers=other)).json()["code"] == 1002
    assert (await client.get(BASE + "/admin/demand/list", headers=other)).json()["code"] == 403
    admin_login = await client.post(BASE + "/auth/dev-login", json={"name": "管理员", "wecomUserid": "mvp-admin"})
    admin = {"Authorization": "Bearer " + admin_login.json()["data"]["accessToken"]}
    assert admin_login.json()["data"]["user"]["isAdmin"]
    assert (await client.get(BASE + "/admin/demand/list?type=TECH", headers=admin)).json()["data"]["total"] == 1
    file = await client.get(BASE + "/admin/demand/export.xlsx?type=TECH", headers=admin)
    sheet = load_workbook(BytesIO(file.content)).active
    assert sheet.title == "TECH" and any(c.value == "=SUM(1,2)" and c.data_type == "s" for row in sheet for c in row)
    assert (await client.get(BASE + "/admin/demand/export.xlsx")).status_code == 401
    assert (await client.put(f"{BASE}/demand/{draft['id']}", headers=admin, json={"expectedRevision": 1, "title": "管理员覆盖"})).json()["code"] == 1002


async def test_invalid_fields_and_clear_protected(client, auth_headers):
    draft = await create(client, auth_headers, demandTypeCode="TECH", title="手动标题")
    for fields in [{"expectDeliveryAt": "2026-99-20"}, {"elements": {"A": {"techSubtype": "INVALID"}}}, {"elements": {"C": {"useScenario": 123}}}, {"status": "SUBMITTED"}]:
        response = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, **fields})
        assert response.json()["code"] == 400, response.text
    clear = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "title": "", "fieldSources": {"title": "default"}})
    assert clear.json()["data"]["title"] is None and clear.json()["data"]["fieldSources"]["title"] == "user"


async def test_mysql_date_optional_whitespace_and_long_subtype(client, auth_headers):
    draft = await create(client, auth_headers, demandTypeCode="MATL", ext={"materialSubtype": "物料子类文字" * 20})
    assert draft["subtypeCode"] is None and len(draft["ext"]["materialSubtype"]) > 32
    response = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "expectDeliveryAt": "0001-01-01"})
    assert response.json()["code"] == 400
    response = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "expectDeliveryAt": "  ", "ext": {"quantity": "  "}})
    assert response.json()["code"] == 0, response.text
    assert response.json()["data"]["expectDeliveryAt"] is None
    for demand_type, subtype in [("MATL", "materialSubtype"), ("TRAIN", "trainingSubtype")]:
        row = await create(client, auth_headers, demandTypeCode=demand_type, ext={subtype: "很长的子类描述" * 10})
        markdown = await client.get(f"{BASE}/demand/{row['id']}/export.md", headers=auth_headers)
        assert "很长的子类描述" in markdown.text
