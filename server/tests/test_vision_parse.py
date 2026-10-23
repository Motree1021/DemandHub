"""AI 图片识别（2026-10-22 拍板）：purpose=parse 上传校验、转写编排（成功/无字/失败/审核拦截/整理失败降级）、
转写文本走 guide 对话链路（trigger=vision 前缀）、限额共用与权限矩阵。"""
import json
from uuid import uuid4

import pytest

from app.agent.llm_client import LlmContentRejected, LlmUnavailable
from app.core.errors import ErrorCode

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


async def make_session(client, headers, demand_id):
    response = await client.post(BASE + "/agent/session", headers=headers,
                                 json={"demandId": demand_id, "scene": "SUBMIT_GUIDE"})
    assert response.json()["code"] == 0, response.text
    return response.json()["data"]["id"]


async def upload_parse(client, headers, demand_id, name, payload):
    return await client.post(f"{BASE}/demand/{demand_id}/attachments?purpose=parse", headers=headers,
                             files={"file": (name, payload, "application/octet-stream")})


async def messages(client, headers, session_id):
    return (await client.get(f"{BASE}/agent/session/{session_id}/messages", headers=headers)).json()["data"]


@pytest.fixture
def mock_transcribe(monkeypatch):
    """编排测试统一拦转写层：默认返回一段聊天转写文本。"""
    from app.services import vision_service
    state = {"calls": 0, "result": "张三: 报表想加个按机构导出\n李四: 下周要", "error": None}

    async def fake(payload: bytes, ext: str):
        state["calls"] += 1
        if state["error"] is not None:
            raise state["error"]
        return state["result"]

    monkeypatch.setattr(vision_service, "transcribe_image", fake)
    return state


@pytest.fixture
def mock_guide_execute(monkeypatch):
    """拦 guide 整理链路：记录 trigger，产出一条固定的 ASSISTANT 整理回复（带 vision 前缀由 policy 保证，
    这里直接以前缀文本模拟，校验编排层 trigger 透传与异常兜底）。"""
    from app.agent.guide import GuideService
    state = {"calls": [], "error": None}

    async def fake(self, req, *, trigger="dialog"):
        state["calls"].append({"trigger": trigger, "message": req.message, "requestId": req.request_id})
        if state["error"] is not None:
            raise state["error"]
        from app.services import session_service
        async with self.db.begin():
            await session_service.append(self.db, req.session_id, "USER", req.message, request_id=req.request_id)
            await session_service.append(self.db, req.session_id, "ASSISTANT",
                                         "我从图片里读到了内容，先帮你整理了一下。还有哪些字段要确认？",
                                         {"kind": "visionReply"}, request_id=req.request_id)

    monkeypatch.setattr(GuideService, "execute", fake)
    return state


# ---- transcribe_image 转写层 ----


async def test_transcribe_returns_text(monkeypatch):
    from app.services import vision_service
    seen = {}

    class FakeLlm:
        def on_success(self):
            seen["success"] = True

        async def complete_vision(self, messages):
            seen["messages"] = messages
            return "  张三: 你好  "

    monkeypatch.setattr(vision_service, "get_llm_client", lambda: FakeLlm())
    text = await vision_service.transcribe_image(b"png-bytes", "png")
    assert text == "张三: 你好"
    content = seen["messages"][0]["content"]
    assert content[0]["type"] == "text" and "转写" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert seen["success"] is True  # 业务校验成功清零熔断计数


async def test_transcribe_no_text_returns_none(monkeypatch):
    from app.services import vision_service

    class FakeLlm:
        def on_success(self):
            pass

        async def complete_vision(self, messages):
            return "NO_TEXT"

    monkeypatch.setattr(vision_service, "get_llm_client", lambda: FakeLlm())
    assert await vision_service.transcribe_image(b"png-bytes", "jpg") is None


async def test_transcribe_truncates_to_message_limit(monkeypatch):
    from app.services import vision_service

    class FakeLlm:
        def on_success(self):
            pass

        async def complete_vision(self, messages):
            return "长" * 25000

    monkeypatch.setattr(vision_service, "get_llm_client", lambda: FakeLlm())
    text = await vision_service.transcribe_image(b"png-bytes", "webp")
    assert text is not None and len(text) == 20000


# ---- _shrink_for_vision 送模型前压缩（2026-10-23：真机照片原图解析 30s+ 超时根因修复） ----


def test_shrink_downscales_large_image():
    from io import BytesIO

    from PIL import Image

    from app.services import vision_service
    buffer = BytesIO()
    Image.new("RGB", (2000, 1000), "white").save(buffer, format="PNG")
    original = buffer.getvalue()
    shrunk, ext = vision_service._shrink_for_vision(original, "png")
    image = Image.open(BytesIO(shrunk))
    # 压缩契约是「长边压到 1600 + 重编码 JPEG」（纯色合成图上 PNG 字节数可能更小，不断言体积）
    assert max(image.size) == 1600 and image.format == "JPEG" and ext == "jpg"


def test_shrink_keeps_small_image_and_undecodable_bytes():
    from io import BytesIO

    from PIL import Image

    from app.services import vision_service
    # 小图不压：字节与扩展名原样
    buffer = BytesIO()
    Image.new("RGB", (800, 600), "white").save(buffer, format="JPEG")
    original = buffer.getvalue()
    payload, ext = vision_service._shrink_for_vision(original, "jpg")
    assert payload == original and ext == "jpg"
    # 解码失败原样返回（交给模型侧报错口径，不在压缩层拦截）
    payload, ext = vision_service._shrink_for_vision(b"not-an-image", "png")
    assert payload == b"not-an-image" and ext == "png"


# ---- purpose=parse 上传校验 ----


async def test_parse_rejects_doc(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers)
    response = await upload_parse(client, auth_headers, draft["id"], "需求说明.pdf", PDF)
    assert response.json()["code"] == 400
    assert "仅图片支持 AI 识别" in response.json()["message"]


async def test_parse_rejects_invalid_purpose(client, auth_headers, attachment_dir):
    draft = await create(client, auth_headers)
    response = await client.post(f"{BASE}/demand/{draft['id']}/attachments?purpose=ocr", headers=auth_headers,
                                 files={"file": ("logo.png", PNG, "application/octet-stream")})
    assert response.json()["code"] == 400


async def test_parse_counts_same_limit(client, auth_headers, attachment_dir, mock_transcribe, mock_guide_execute):
    """识别图片与附件共用同一 5 个限额（2026-10-22 拍板）：archive 传 4 个后 parse 第 5 个成功、第 6 个被拒。"""
    draft = await create(client, auth_headers)
    await make_session(client, auth_headers, draft["id"])
    for index in range(4):
        response = await client.post(f"{BASE}/demand/{draft['id']}/attachments", headers=auth_headers,
                                     files={"file": (f"a{index}.png", PNG, "application/octet-stream")})
        assert response.json()["code"] == 0, response.text
    assert (await upload_parse(client, auth_headers, draft["id"], "p5.png", PNG)).json()["code"] == 0
    response = await upload_parse(client, auth_headers, draft["id"], "p6.png", PNG)
    assert response.json()["code"] == 400 and "最多上传 5 个" in response.json()["message"]


async def test_parse_rejects_flowing_demand(client, auth_headers, attachment_dir):
    """流转中需求不可用 AI 图片识别（权限矩阵先拦：提报人非处理人，按既有口径拒绝）。"""
    draft = await create(client, auth_headers)
    await make_session(client, auth_headers, draft["id"])
    # 补齐必填走提交链路成本太高，直接改库状态模拟流转中
    from sqlalchemy import select

    from app.db.models import Demand
    from app.db.session import get_session_factory
    async with get_session_factory()() as db:
        async with db.begin():
            demand = (await db.execute(select(Demand).where(Demand.id == draft["id"]))).scalar_one()
            demand.status = "ANALYZING"
    response = await upload_parse(client, auth_headers, draft["id"], "截图.png", PNG)
    assert response.json()["code"] == 1001


# ---- run_vision_parse 编排 ----


async def test_parse_success_flow(client, auth_headers, attachment_dir, mock_transcribe, mock_guide_execute):
    """成功链路：PARSED 落库 + 气泡回写 parsed 标记 + 转写文本走 guide（trigger=vision）。"""
    draft = await create(client, auth_headers)
    session_id = await make_session(client, auth_headers, draft["id"])
    response = await upload_parse(client, auth_headers, draft["id"], "聊天截图.png", PNG)
    data = response.json()
    assert data["code"] == 0, response.text
    assert data["data"]["purpose"] == "parse" and data["data"]["parseStatus"] == "PARSED"
    assert mock_transcribe["calls"] == 1
    # 整理链路 trigger 透传 vision；转写文本包装为用户消息
    assert len(mock_guide_execute["calls"]) == 1
    call = mock_guide_execute["calls"][0]
    assert call["trigger"] == "vision"
    assert call["requestId"] == f"vision-{data['data']['id']}"
    assert "聊天截图.png" in call["message"] and "张三: 报表想加个按机构导出" in call["message"]
    # 会话：附件气泡（purpose=parse、parsed 已回写）+ 转写用户消息 + 整理回复
    rows = await messages(client, auth_headers, session_id)
    bubble = next(r for r in rows if r["content"] == "[上传附件] 聊天截图.png")
    bubble_payload = json.loads(bubble["structuredPayload"])
    assert bubble_payload["purpose"] == "parse" and bubble_payload["parsed"] is True
    assert not any(json.loads(r["structuredPayload"] or "{}").get("kind") == "attachmentReceipt" for r in rows)
    assert any("图片「聊天截图.png」里的内容" in r["content"] for r in rows if r["role"] == "USER")
    assert rows[-1]["content"].startswith("我从图片里读到了内容，先帮你整理了一下。")
    # 转写文本入库供受理方追溯
    detail = (await client.get(f"{BASE}/demand/{draft['id']}", headers=auth_headers)).json()["data"]
    attachment = next(a for a in detail["attachments"] if a["id"] == data["data"]["id"])
    assert attachment["parseStatus"] == "PARSED"


async def test_parse_no_text_degrades(client, auth_headers, attachment_dir, mock_transcribe, mock_guide_execute):
    """无字图片：标 NO_TEXT，降级为普通附件（回执+规则接续），不进整理链路。"""
    mock_transcribe["result"] = None
    draft = await create(client, auth_headers)
    session_id = await make_session(client, auth_headers, draft["id"])
    response = await upload_parse(client, auth_headers, draft["id"], "风景照.png", PNG)
    data = response.json()
    assert data["code"] == 0, response.text
    assert data["data"]["parseStatus"] == "NO_TEXT"
    assert not mock_guide_execute["calls"]
    rows = await messages(client, auth_headers, session_id)
    receipt = next(r for r in rows if json.loads(r["structuredPayload"] or "{}").get("kind") == "attachmentReceipt")
    assert "没有识别到文字" in receipt["content"] and "已作为附件存档" in receipt["content"]


async def test_parse_llm_unavailable_degrades(client, auth_headers, attachment_dir, mock_transcribe, mock_guide_execute):
    """识别失败（超时/5xx/熔断）：标 FAILED 降级存档，回执话术引导换图或文字补充，请求不失败。"""
    mock_transcribe["error"] = LlmUnavailable()
    draft = await create(client, auth_headers)
    session_id = await make_session(client, auth_headers, draft["id"])
    response = await upload_parse(client, auth_headers, draft["id"], "截图.png", PNG)
    data = response.json()
    assert data["code"] == 0, response.text
    assert data["data"]["parseStatus"] == "FAILED"
    assert not mock_guide_execute["calls"]
    rows = await messages(client, auth_headers, session_id)
    receipt = next(r for r in rows if json.loads(r["structuredPayload"] or "{}").get("kind") == "attachmentReceipt")
    assert "识别失败" in receipt["content"] and "已作为附件存档" in receipt["content"]


async def test_parse_content_rejected_goes_1405(client, auth_headers, attachment_dir, mock_transcribe, mock_guide_execute):
    """审核拦截：附件保留标 FAILED，1405 直达用户（与对话审核同口径，提示改写）。"""
    mock_transcribe["error"] = LlmContentRejected()
    draft = await create(client, auth_headers)
    await make_session(client, auth_headers, draft["id"])
    response = await upload_parse(client, auth_headers, draft["id"], "截图.png", PNG)
    assert response.json()["code"] == 1405
    assert not mock_guide_execute["calls"]
    # 附件已保存占限额
    detail = (await client.get(f"{BASE}/demand/{draft['id']}", headers=auth_headers)).json()["data"]
    assert len(detail["attachments"]) == 1 and detail["attachments"][0]["parseStatus"] == "FAILED"


async def test_parse_guide_failure_fallback(client, auth_headers, attachment_dir, mock_transcribe, mock_guide_execute):
    """整理阶段失败（1401/409 等）：转写文本已入库（PARSED），兜底回执告知内容已记录，不阻塞提报。"""
    from app.core.errors import BizError
    mock_guide_execute["error"] = BizError(ErrorCode.AI_SERVICE_UNAVAILABLE)
    draft = await create(client, auth_headers)
    session_id = await make_session(client, auth_headers, draft["id"])
    response = await upload_parse(client, auth_headers, draft["id"], "截图.png", PNG)
    data = response.json()
    assert data["code"] == 0, response.text
    assert data["data"]["parseStatus"] == "PARSED"
    rows = await messages(client, auth_headers, session_id)
    receipt = next(r for r in rows if json.loads(r["structuredPayload"] or "{}").get("kind") == "attachmentReceipt")
    assert "内容我已记录" in receipt["content"] and "整理时出了点问题" in receipt["content"]
