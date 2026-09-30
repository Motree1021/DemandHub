from io import BytesIO
from uuid import uuid4

from openpyxl import load_workbook

BASE = "/demandhub-api"


async def create(client, headers, **fields):
    response = await client.post(BASE + "/demand", headers=headers, json={"clientRequestId": str(uuid4()), **fields})
    assert response.json()["code"] == 0, response.text
    return response.json()["data"]


async def test_incomplete_draft_full_lifecycle(client, auth_headers):
    draft = await create(client, auth_headers)
    assert draft["demandNo"] is None and draft["demandTypeCode"] is None
    response = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=auth_headers, json={"expectedRevision": 0})
    assert response.json()["code"] == 400
    response = await client.put(f"{BASE}/demand/{draft['id']}", headers=auth_headers, json={"expectedRevision": 0, "title": "持仓数据报表", "demandTypeCode": "TECH", "content": "每天晨会前需要自动整理渠道持仓数据，替代手工Excel统计", "ext": {"businessScenario": "每周客户经理查询各渠道持仓并整理晨会材料", "acceptanceCriteria": "连续7天对账误差为0", "valueImpact": "20人每天节省40分钟", "unknown": "filtered"}})
    assert response.json()["code"] == 0, response.text
    updated = response.json()["data"]
    assert updated["fieldSources"]["title"] == "user" and "unknown" not in updated["ext"]
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
    draft = await create(client, auth_headers, demandTypeCode="TECH", title="=FORMULA", content="业务描述", ext={"businessScenario": "=SUM(1,2)"})
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
    for fields in [{"expectDeliveryAt": "2026-99-20"}, {"ext": {"techSubtype": "INVALID"}}, {"ext": {"businessScenario": 123}}, {"status": "SUBMITTED"}]:
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
