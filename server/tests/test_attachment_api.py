"""需求附件（阶段一）：白名单+魔数+限额+DRAFT 校验、鉴权下载、软删、会话固定回执、导出附件清单。"""
import json
from urllib.parse import unquote
from uuid import uuid4

import pytest

BASE = "/demandhub-api"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.7\n%%_Test\n" + b"0" * 32


@pytest.fixture
def attachment_dir(monkeypatch, tmp_path):
    from app.config import get_settings
    directory = tmp_path / "att"
    monkeypatch.setattr(get_settings(), "attachment_dir", str(directory))
    return directory


async def create(client, headers, **fields):
    response = await client.post(BASE + "/demand", headers=headers, json={"clientRequestId": str(uuid4()), **fields})
    assert response.json()["code"] == 0, response.text
    return response.json()["data"]


async def upload(client, headers, demand_id, name, payload):
    return await client.post(f"{BASE}/demand/{demand_id}/attachments", headers=headers,
                             files={"file": (name, payload, "application/octet-stream")})


async def test_upload_png_and_receipt(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers)
    session = await client.post(BASE + "/agent/session", headers=auth_headers,
                                json={"demandId": draft["id"], "scene": "SUBMIT_GUIDE"})
    assert session.json()["code"] == 0, session.text
    session_id = session.json()["data"]["id"]
    response = await upload(client, auth_headers, draft["id"], "logo.png", PNG)
    data = response.json()
    assert data["code"] == 0, response.text
    assert data["data"] == {"id": data["data"]["id"], "demandId": draft["id"], "fileName": "logo.png",
                            "kind": "IMAGE", "kindLabel": "图片", "size": len(PNG),
                            "bizType": "DEMAND", "bizId": draft["id"],
                            "createdAt": data["data"]["createdAt"]}
    # 文件落盘在配置目录下（storage_key 不外泄），路径不含原始文件名的路径部分
    stored = list((attachment_dir / str(draft["id"])).glob("*.png"))
    assert len(stored) == 1 and stored[0].read_bytes() == PNG
    # 固定回执不调模型：上传 USER 消息 + AI 回执 ASSISTANT 消息成对落会话
    messages = (await client.get(f"{BASE}/agent/session/{session_id}/messages", headers=auth_headers)).json()["data"]
    assert messages[-3]["content"] == "[上传附件] logo.png"
    assert messages[-3]["structuredPayload"] and json.loads(messages[-3]["structuredPayload"])["kind"] == "attachment"
    assert messages[-2]["content"].startswith("已收到附件「logo.png」")
    assert json.loads(messages[-2]["structuredPayload"])["kind"] == "attachmentReceipt"
    # 回执后的流程接续（2026-10-19 拍板）：AI 不停在回执，规则层续上下一追问（首个必填缺口），对话不中断
    follow = json.loads(messages[-1]["structuredPayload"])
    assert "kind" not in follow  # 接续消息无 kind，可被 guide.prepare 认作下一轮 previous 快照
    assert follow["askedTarget"] and follow["elements"] and follow["structured"] is not None
    assert follow["revision"] == draft["revision"]  # 附件不改表单，revision 不变，前端质量清单可回放
    assert messages[-1]["content"] == follow["reply"]


async def test_upload_rejects_bad_type_magic_size(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers)
    # 白名单外扩展名
    assert (await upload(client, auth_headers, draft["id"], "virus.exe", b"MZ")).json()["code"] == 400
    # 无扩展名 / 空文件名
    assert (await upload(client, auth_headers, draft["id"], "README", b"md")).json()["code"] == 400
    # 魔数不符：文本伪装 png
    assert (await upload(client, auth_headers, draft["id"], "fake.png", b"not a png")).json()["code"] == 400
    # 超过 10MB
    oversized = PNG[:8] + b"x" * (10 * 1024 * 1024)
    assert (await upload(client, auth_headers, draft["id"], "big.png", oversized)).json()["code"] == 400
    # 路径穿越的文件名只取末段，正常落库
    ok = await upload(client, auth_headers, draft["id"], "C:\\fake\\公司logo.png", PNG)
    assert ok.json()["code"] == 0 and ok.json()["data"]["fileName"] == "公司logo.png"


async def test_upload_count_limit_and_soft_delete(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers)
    ids = []
    for i in range(5):
        response = await upload(client, auth_headers, draft["id"], f"图{i}.png", PNG)
        assert response.json()["code"] == 0, response.text
        ids.append(response.json()["data"]["id"])
    # 第 6 个被拒
    assert (await upload(client, auth_headers, draft["id"], "六.png", PNG)).json()["code"] == 400
    # 软删后可再传
    removed = await client.delete(f"{BASE}/demand/{draft['id']}/attachments/{ids[0]}", headers=auth_headers)
    assert removed.json()["code"] == 0, removed.text
    again = await upload(client, auth_headers, draft["id"], "新的.png", PNG)
    assert again.json()["code"] == 0
    # 已删的不可重复删、不可下载
    assert (await client.delete(f"{BASE}/demand/{draft['id']}/attachments/{ids[0]}", headers=auth_headers)).json()["code"] == 404
    assert (await client.get(f"{BASE}/demand/{draft['id']}/attachments/{ids[0]}/download", headers=auth_headers)).json()["code"] == 404
    # 列表只剩 5 个 ACTIVE
    listed = (await client.get(f"{BASE}/demand/{draft['id']}/attachments", headers=auth_headers)).json()["data"]
    assert len(listed) == 5 and all(item["id"] != ids[0] for item in listed)


async def test_submitted_demand_upload_and_delete_blocked(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers, title="换logo", demandTypeCode="TECH",
        content="把系统logo换成公司新版logo，橙蓝色为主", urgency="NORMAL",
        elements={"A": {"techSubtype": "OPS_OPT"}, "C": {"userRole": "客户经理", "userGoal": "登录时看到新logo形象",
            "useScenario": "每次登录系统时客户经理看到新logo", "painPoint": "旧logo与公司风格不一致"},
            "D": {"functionDescription": "替换系统logo为橙蓝风格", "inputOutput": "输入新logo图片输出展示页面",
                  "acceptanceCriteria": "名称显示为话术生成与分发系统，logo为橙蓝公司风格"}})
    uploaded = await upload(client, auth_headers, draft["id"], "ref.png", PNG)
    assert uploaded.json()["code"] == 0
    attachment_id = uploaded.json()["data"]["id"]
    # 上传不修改 revision，提交仍按 revision=0
    submitted = await client.post(f"{BASE}/demand/{draft['id']}/submit", headers=auth_headers, json={"expectedRevision": 0})
    assert submitted.json()["code"] == 0, submitted.text
    # 已提交：不可传、不可删（附件需随需求可追溯）
    assert (await upload(client, auth_headers, draft["id"], "after.png", PNG)).json()["code"] == 1001
    assert (await client.delete(f"{BASE}/demand/{draft['id']}/attachments/{attachment_id}", headers=auth_headers)).json()["code"] == 1001
    # 已提交附件仍可下载（受理方查看）
    download = await client.get(f"{BASE}/demand/{draft['id']}/attachments/{attachment_id}/download", headers=auth_headers)
    assert download.status_code == 200 and download.content == PNG


async def test_download_auth_and_admin_visibility(client, auth_headers, attachment_dir, admin_headers):
    draft = await create(client, auth_headers)
    uploaded = await upload(client, auth_headers, draft["id"], "参考.pdf", PDF)
    attachment_id = uploaded.json()["data"]["id"]
    # 本人可下载，中文名走 RFC5987 编码（FileResponse 输出小写 utf-8''）
    mine = await client.get(f"{BASE}/demand/{draft['id']}/attachments/{attachment_id}/download", headers=auth_headers)
    assert mine.status_code == 200 and mine.content == PDF
    disposition = mine.headers["content-disposition"]
    assert unquote(disposition.split("''", 1)[1]) == "参考.pdf"
    # 他人不可见（与需求详情同口径）
    login = await client.post(BASE + "/auth/dev-login", json={"name": "其他用户", "wecomUserid": "other-user"})
    other = {"Authorization": "Bearer " + login.json()["data"]["accessToken"]}
    assert (await client.get(f"{BASE}/demand/{draft['id']}/attachments", headers=other)).json()["code"] == 1002
    assert (await client.get(f"{BASE}/demand/{draft['id']}/attachments/{attachment_id}/download", headers=other)).json()["code"] == 1002
    # ADMIN 可见可下载（受理方视角）
    listed = (await client.get(f"{BASE}/demand/{draft['id']}/attachments", headers=admin_headers)).json()
    assert listed["code"] == 0 and listed["data"][0]["fileName"] == "参考.pdf"
    assert (await client.get(f"{BASE}/demand/{draft['id']}/attachments/{attachment_id}/download", headers=admin_headers)).status_code == 200


async def test_detail_and_export_include_attachments(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers, title="调整logo与系统名称",
                         content="帮我调整话术系统的logo和系统名称，logo橙蓝色为主，名称改为：话术生成与分发系统")
    await upload(client, auth_headers, draft["id"], "公司logo.png", PNG)
    await upload(client, auth_headers, draft["id"], "规范说明.md", "# 名称规范\n话术生成与分发系统".encode())
    detail = (await client.get(f"{BASE}/demand/{draft['id']}", headers=auth_headers)).json()["data"]
    assert [item["fileName"] for item in detail["attachments"]] == ["公司logo.png", "规范说明.md"]
    assert detail["attachments"][0]["kindLabel"] == "图片" and detail["attachments"][1]["kindLabel"] == "文档"
    markdown = await client.get(f"{BASE}/demand/{draft['id']}/export.md", headers=auth_headers)
    assert "## 附件" in markdown.text and "公司logo.png | 图片" in markdown.text and "规范说明.md | 文档" in markdown.text


def test_user_supplements_excludes_attachment_messages():
    from app.services.export import user_supplements
    messages = [
        {"role": "USER", "content": "原始需求描述", "structuredPayload": None, "createdAt": "2026-10-11 10:00:00"},
        {"role": "USER", "content": "[上传附件] 公司logo.png",
         "structuredPayload": json.dumps({"kind": "attachment", "attachmentId": 1, "fileName": "公司logo.png"}),
         "createdAt": "2026-10-11 10:01:00"},
        {"role": "ASSISTANT", "content": "已收到附件「公司logo.png」…",
         "structuredPayload": json.dumps({"kind": "attachmentReceipt", "attachmentId": 1}), "createdAt": "2026-10-11 10:01:01"},
        {"role": "USER", "content": "补充：名称改为话术生成与分发系统", "structuredPayload": None, "createdAt": "2026-10-11 10:02:00"},
    ]
    supplements = user_supplements("原始需求描述", messages)
    assert [m["content"] for m in supplements] == ["补充：名称改为话术生成与分发系统"]
