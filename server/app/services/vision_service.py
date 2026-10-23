"""AI 图片识别（2026-10-22 拍板）：视觉模型只做「图→文本」转写，文本落地后走既有对话链路整理。

口径（对 2026-10-11「AI 不看附件内容」拍板的修订）：
- 默认不看附件内容（purpose=archive，口径不变）；用户显式选择「让 AI 读懂图片」（purpose=parse）才调视觉模型
- 视觉模型仅转写：聊天截图按「说话人: 内容」时序逐条提取；其他含字图直接完整提取；无字返回 NO_TEXT；不评判不总结
- 转写文本作为一条用户消息走既有 guide 对话链路（trigger=vision），判型/口径/要素抽取/追问零改动
- 同步解析最长 60s；失败/无字/超时自动降级为普通附件（固定话术回执+流程接续），不阻塞提报
- 转写文本同时入库 demand_attachment.parsed_text，供受理方追溯
"""
import base64
import logging
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.agent.llm_client import LlmContentRejected, LlmUnavailable, get_llm_client
from app.core.errors import BizError, ErrorCode
from app.db.models import AgentMessage, Demand, DemandAttachment, now
from app.services import attachment_service

logger = logging.getLogger(__name__)

NO_TEXT = "NO_TEXT"

# 转写提示词（拍板口径：只转写不评判；聊天截图时序逐条；含字图直接提取；无字 NO_TEXT）
PARSE_PROMPT = """你在帮一位员工整理需求提报材料。请阅读这张图片并提取其中的文字内容。

要求：
1. 如果是聊天截图（微信/企业微信等），按时间顺序逐条转写，格式为「说话人: 内容」，每条一行，不要遗漏、不要合并；
2. 如果是其他含文字的图片（文档拍照/白板/便签/屏幕截图等），直接完整转写文字，保留原有分段结构；
3. 只做转写：不总结、不评价、不补充图片里没有的内容；
4. 如果图片中没有任何可辨认的文字，只回复 NO_TEXT 四个字母。"""

_MIME_BY_EXT = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "webp": "webp"}

# 大图压缩（2026-10-23 实测：真机微信照片原图 1.2MB 解析耗时 30s+，超过原 30s 超时）：
# 送模型前长边压到 1600px 以内并重编码 JPEG——聊天文字仍清晰，耗时降到秒级、视觉 token 更省；
# 仅压缩送模型的载荷，附件原件不受任何影响
_VISION_MAX_SIDE = 1600


def _shrink_for_vision(payload: bytes, ext: str) -> tuple[bytes, str]:
    """长边超过 1600px 的图压缩后再送模型；小图或解码失败（交给模型侧报错口径）原样返回。"""
    try:
        image = Image.open(BytesIO(payload))
    except Exception:
        return payload, ext
    if max(image.size) <= _VISION_MAX_SIDE:
        return payload, ext
    image.thumbnail((_VISION_MAX_SIDE, _VISION_MAX_SIDE), Image.LANCZOS)
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=85)
    return buffer.getvalue(), "jpg"


async def transcribe_image(payload: bytes, ext: str) -> str | None:
    """图→文本转写。返回 None 表示图中无文字；上游故障/审核拦截抛给编排层。
    输出非 NO_TEXT 时截断到 20000 字符（对话消息上限），防超长截图撑爆契约。"""
    client = get_llm_client()
    payload, ext = _shrink_for_vision(payload, ext)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": PARSE_PROMPT},
            {"type": "image_url", "image_url": {
                "url": f"data:image/{_MIME_BY_EXT.get(ext, 'jpeg')};base64,{base64.b64encode(payload).decode()}",
            }},
        ],
    }]
    raw = (await client.complete_vision(messages)).strip()
    # HTTP 成功且拿到模型输出即算业务成功（NO_TEXT 是合法输出），清零熔断计数（与 chat 口径一致）
    client.on_success()
    if not raw or (raw.upper().startswith(NO_TEXT) and len(raw) <= 20):
        return None
    return raw[:20000]


async def run_vision_parse(db, user, demand_id: int, attachment_id: int, payload: bytes) -> None:
    """vision 编排（API 层在附件落库提交后调用，不入其事务）：
    解析成功 → 落 parse 结果 + 附件气泡「AI 已读取」标记 + 转写文本走 guide 对话链路整理；
    失败/无字 → 降级为普通附件（回执+流程接续，与 archive 同链路）。除审核拦截（1405 直达用户）外，
    任何异常都不让上传请求失败——附件已保存，识别失败不阻塞提报。"""
    # 读取也包在 begin 里：ORM 读取默认 autobegin 挂起读事务，后续各写入段的 begin 会与之冲突
    # （expire_on_commit=False，提交后对象属性仍可用）
    async with db.begin():
        demand = await db.get(Demand, demand_id)
        row = await db.get(DemandAttachment, attachment_id)
    if demand is None or row is None or row.purpose != "parse":
        return

    async def degrade(note: str, status: str) -> None:
        async with db.begin():
            row.parse_status = status
            await attachment_service.archive_receipt(db, user, demand, row, note)

    failed_note = f"图片「{row.file_name}」识别失败了，已作为附件存档，会随需求一并提交。可以换一张试试，或用文字补充说明。"
    if demand.session_id is None:
        # 无会话可写（前端上传前已确保会话存在，此分支纯防御）：仅标记失败，不写消息不调模型
        async with db.begin():
            row.parse_status = "FAILED"
        return
    try:
        text = await transcribe_image(payload, row.file_ext)
    except LlmContentRejected:
        # 审核拦截（2026-10-15 拍板口径）：附件已保留，标 FAILED，1405 直达用户提示改写
        async with db.begin():
            row.parse_status = "FAILED"
        raise BizError(ErrorCode.AI_CONTENT_REJECTED) from None
    except LlmUnavailable:
        await degrade(failed_note, "FAILED")
        return
    except Exception as exc:  # 防御：视觉链路任何意外都不阻塞提报（LlmUnavailable 内部已留痕，不重复记）
        logger.warning("vision 解析异常 demand=%s attachment=%s %s: %s", demand_id, attachment_id, type(exc).__name__, exc)
        await degrade(failed_note, "FAILED")
        return
    if text is None:
        await degrade(f"图片「{row.file_name}」里没有识别到文字，已作为附件存档，会随需求一并提交。需要的话可以用文字补充说明。", "NO_TEXT")
        return

    # 解析成功：落 parse 结果；附件气泡回写 parsed 标记（前端「AI 已读取」标签）
    async with db.begin():
        row.parse_status = "PARSED"
        row.parsed_text = text
        row.parsed_at = now()
        bubble = (await db.execute(select(AgentMessage).where(
            AgentMessage.session_id == demand.session_id,
            AgentMessage.request_id == f"attach-{row.id}",
            AgentMessage.role == "USER",
        ))).scalar_one_or_none()
        if bubble is not None:
            bubble_payload = dict(bubble.structured_payload or {})
            bubble_payload["parsed"] = True
            bubble.structured_payload = bubble_payload

    # 转写文本作为一条用户消息走既有对话链路：判型/口径/要素抽取/追问零改动（trigger=vision 给回复前缀）。
    # 消息原文让用户看见 AI 读到了什么——误识别在后续追问中自然纠正（不做单独确认环节）
    from app.agent.guide import GuideService
    from app.agent.schemas import GuideChatRequest

    message = f"以下是我上传的图片「{row.file_name}」里的内容：\n{text}"
    request = GuideChatRequest(
        demand_id=demand.id, session_id=demand.session_id,
        request_id=f"vision-{row.id}", revision=demand.revision, message=message,
    )
    try:
        await GuideService(db, user).execute(request, trigger="vision")
    except BizError as error:
        # 整理阶段失败（1401 上游故障/409 并发冲突等）：转写文本已入库随需求提交，回执兜底不阻塞提报
        logger.warning("vision 整理阶段失败 demand=%s attachment=%s code=%s", demand_id, attachment_id, error.code)
        async with db.begin():
            await attachment_service.archive_receipt(
                db, user, demand, row,
                f"图片「{row.file_name}」的内容我已记录，会随需求一并提交；但自动整理时出了点问题，你可以直接跟我说一遍，或在表单里补充。")
    except Exception as exc:
        logger.warning("vision 整理阶段异常 demand=%s attachment=%s %s: %s", demand_id, attachment_id, type(exc).__name__, exc)
        async with db.begin():
            await attachment_service.archive_receipt(
                db, user, demand, row,
                f"图片「{row.file_name}」的内容我已记录，会随需求一并提交；但自动整理时出了点问题，你可以直接跟我说一遍，或在表单里补充。")
