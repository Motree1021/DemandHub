"""需求附件：白名单+魔数校验，本地目录存储（storage_key 不外泄），上传写会话固定回执（不调模型）。

业务口径（微需求快速通道·阶段一，2026-10-11 拍板）：
- 图片 png/jpg/jpeg/webp + 文档 md/pdf/doc/docx/ppt/pptx；单文件 10MB、每条需求最多 5 个
- 仅 DRAFT 态可传可删；提交后附件随需求流转不可删，保证受理方追溯
- AI 不看附件内容（不做多模态）：模型只知道文件名（会话回执），内容给受理方看
"""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select

from app.config import get_settings
from app.core.deps import is_admin
from app.core.errors import BizError, ErrorCode
from app.core.result import encode
from app.db.models import Demand, DemandAttachment
from app.services import session_service

MAX_SIZE = 10 * 1024 * 1024
MAX_COUNT = 5
IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
DOC_EXTS = {"md", "pdf", "doc", "docx", "ppt", "pptx"}
KIND_LABELS = {"IMAGE": "图片", "DOC": "文档"}


def check_magic(ext: str, head: bytes) -> bool:
    """按扩展名校验文件头魔数，防扩展名伪造；md 为纯文本无魔数，以不含 NUL 字节作二进制排除。"""
    if ext == "png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == "webp":
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if ext == "pdf":
        return head.startswith(b"%PDF-")
    if ext in ("docx", "pptx"):
        return head.startswith(b"PK\x03\x04")
    if ext in ("doc", "ppt"):
        return head.startswith(b"\xd0\xcf\x11\xe0")
    if ext == "md":
        return b"\x00" not in head
    return False


def storage_path(demand_id: int, storage_key: str, file_ext: str) -> Path:
    return Path(get_settings().attachment_dir) / str(demand_id) / f"{storage_key}.{file_ext}"


async def get_owned_draft(db, user, demand_id: int, *, for_update: bool = False) -> Demand:
    from app.services.demand_service import get_owned_draft

    return await get_owned_draft(db, user, demand_id, for_update=for_update)


async def viewable_demand(db, user, demand_id: int) -> Demand:
    """附件查看/下载权限与需求详情同口径：本人或 ADMIN。"""
    demand = await db.get(Demand, demand_id)
    if demand is None or (demand.submitter_id != user.id and not is_admin(user)):
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    return demand


def serialize_attachment(row: DemandAttachment) -> dict:
    return {
        "id": row.id,
        "demandId": row.demand_id,
        "fileName": row.file_name,
        "kind": row.kind,
        "kindLabel": KIND_LABELS.get(row.kind, row.kind),
        "size": row.size,
        "createdAt": encode(row.created_at),
    }


async def list_attachments(db, demand_id: int) -> list[DemandAttachment]:
    return list(
        (
            await db.execute(
                select(DemandAttachment)
                .where(DemandAttachment.demand_id == demand_id, DemandAttachment.status == "ACTIVE")
                .order_by(DemandAttachment.id)
            )
        ).scalars()
    )


async def serialize_list(db, demand_id: int) -> list[dict]:
    return [serialize_attachment(row) for row in await list_attachments(db, demand_id)]


async def save_attachment(
    db, user, demand_id: int, filename: str | None, payload: bytes
) -> DemandAttachment:
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    if demand.status != "DRAFT":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "草稿已提交或关闭，不能再上传附件")
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or len(name) > 256:
        raise BizError(ErrorCode.PARAM_INVALID, "文件名无效")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    kind = "IMAGE" if ext in IMAGE_EXTS else "DOC" if ext in DOC_EXTS else None
    if kind is None:
        raise BizError(
            ErrorCode.PARAM_INVALID,
            "不支持的文件类型，仅支持图片（png/jpg/jpeg/webp）与文档（md/pdf/doc/docx/ppt/pptx）",
        )
    if not payload:
        raise BizError(ErrorCode.PARAM_INVALID, "文件内容为空")
    if len(payload) > MAX_SIZE:
        raise BizError(ErrorCode.PARAM_INVALID, "文件超过 10MB 上限")
    if not check_magic(ext, payload[:16]):
        raise BizError(ErrorCode.PARAM_INVALID, "文件内容与类型不符，请确认文件完整后重试")
    count = (
        await db.execute(
            select(func.count())
            .select_from(DemandAttachment)
            .where(DemandAttachment.demand_id == demand_id, DemandAttachment.status == "ACTIVE")
        )
    ).scalar_one()
    if count >= MAX_COUNT:
        raise BizError(
            ErrorCode.PARAM_INVALID, f"每条需求最多上传 {MAX_COUNT} 个附件，可先删除不需要的"
        )
    storage_key = uuid4().hex
    path = storage_path(demand_id, storage_key, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    row = DemandAttachment(
        demand_id=demand_id,
        file_name=name,
        kind=kind,
        file_ext=ext,
        size=len(payload),
        storage_key=storage_key,
        uploaded_by=user.id,
    )
    db.add(row)
    await db.flush()
    # AI 固定回执（不调模型）：上传动作写入会话上下文，模型只知文件名不知内容
    if demand.session_id is not None:
        request_id = f"attach-{row.id}"
        await session_service.append(
            db,
            demand.session_id,
            "USER",
            f"[上传附件] {name}",
            {
                "kind": "attachment",
                "attachmentId": row.id,
                "fileName": name,
                "fileKind": kind,
                "size": row.size,
            },
            request_id=request_id,
        )
        await session_service.append(
            db,
            demand.session_id,
            "ASSISTANT",
            f"已收到附件「{name}」，会随需求一并提交给受理方。注意：我暂时看不了图片或文档里的内容，有需要请用文字补充说明。",
            {"kind": "attachmentReceipt", "attachmentId": row.id, "fileName": name},
            request_id=request_id,
        )
    return row


async def get_attachment(
    db, user, demand_id: int, attachment_id: int
) -> tuple[Demand, DemandAttachment]:
    demand = await viewable_demand(db, user, demand_id)
    row = (
        await db.execute(
            select(DemandAttachment).where(
                DemandAttachment.id == attachment_id,
                DemandAttachment.demand_id == demand_id,
                DemandAttachment.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "附件不存在或已删除")
    return demand, row


async def delete_attachment(db, user, demand_id: int, attachment_id: int) -> None:
    # 与上传同口径：仅 DRAFT 态可删；文件本体保留（软删），已流转附件可追溯
    demand = await get_owned_draft(db, user, demand_id, for_update=True)
    if demand.status != "DRAFT":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "草稿已提交或关闭，附件不可删除")
    row = (
        await db.execute(
            select(DemandAttachment).where(
                DemandAttachment.id == attachment_id,
                DemandAttachment.demand_id == demand_id,
                DemandAttachment.status == "ACTIVE",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "附件不存在或已删除")
    row.status = "DELETED"
    await db.flush()
