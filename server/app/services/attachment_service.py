"""需求附件：白名单+魔数校验，本地目录存储（storage_key 不外泄），上传写会话固定回执（不调模型）。

业务口径（微需求快速通道·阶段一，2026-10-11 拍板；P2 扩展 bizType 维持限额口径）：
- 图片 png/jpg/jpeg/webp + 文档 md/pdf/doc/docx/ppt/pptx；单文件 10MB、每条需求最多 5 个
  （5 个限额不分 bizType 统一计数，2026-10-12 拍板维持既有口径）
- bizType 权限矩阵（P2）：
  DEMAND/DRAFT：草稿/待补充态=提报人可传删；流转中=处理人/管理员可传（交付物），提交后提报人不可删；
  SOLUTION：方案作者，方案草稿/在评时可传，仅草稿方案附件可删；
  COMMENT：评论作者随评论上传，上传人或管理员可删；终态（DONE/CLOSED）一律不可传删
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
BIZ_TYPES = {"DRAFT", "DEMAND", "SOLUTION", "COMMENT"}
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


async def viewable_demand(db, user, demand_id: int) -> Demand:
    """附件查看/下载权限与需求详情同口径（P2 统一走流转可见性：提报人/管理员/流转中处理人）。"""
    from app.services.flow_service import get_viewable

    return await get_viewable(db, user, demand_id)


def serialize_attachment(row: DemandAttachment) -> dict:
    return {
        "id": row.id,
        "demandId": row.demand_id,
        "fileName": row.file_name,
        "kind": row.kind,
        "kindLabel": KIND_LABELS.get(row.kind, row.kind),
        "size": row.size,
        "bizType": row.biz_type,
        "bizId": row.biz_id,
        "createdAt": encode(row.created_at),
    }


async def list_attachments(db, demand_id: int, biz_type: str | None = None,
                           biz_id: int | None = None) -> list[DemandAttachment]:
    filters = [DemandAttachment.demand_id == demand_id, DemandAttachment.status == "ACTIVE"]
    if biz_type:
        filters.append(DemandAttachment.biz_type == biz_type)
    if biz_id is not None:
        filters.append(DemandAttachment.biz_id == biz_id)
    return list(
        (await db.execute(select(DemandAttachment).where(*filters).order_by(DemandAttachment.id))).scalars()
    )


async def serialize_list(db, demand_id: int) -> list[dict]:
    return [serialize_attachment(row) for row in await list_attachments(db, demand_id)]


async def _resolve_biz_target(db, user, demand: Demand, biz_type: str, biz_id: int | None) -> tuple[str, int]:
    """校验上传权限矩阵并返回落库 (biz_type, biz_id)。DRAFT 归一为 DEMAND（提报阶段附件随需求流转）。"""
    if biz_type in ("DEMAND", "DRAFT"):
        if demand.status in ("DRAFT", "NEED_INFO"):
            if demand.submitter_id != user.id and not is_admin(user):
                raise BizError(ErrorCode.DEMAND_NOT_FOUND)
        elif demand.status in ("DONE", "CLOSED"):
            raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "已办结的需求不可传附件")
        elif demand.assignee_id != user.id and not is_admin(user):
            # 流转中：仅处理人/管理员可传交付物；提报人保持既有 1001 口径，无关人保持 404 口径
            if demand.submitter_id == user.id:
                raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "草稿已提交或关闭，不能再上传附件")
            raise BizError(ErrorCode.DEMAND_NOT_FOUND)
        return "DEMAND", demand.id
    if biz_id is None:
        raise BizError(ErrorCode.PARAM_INVALID, "bizId 必填")
    if biz_type == "SOLUTION":
        from app.db.models import Solution
        solution = await db.get(Solution, biz_id)
        if solution is None or solution.demand_id != demand.id:
            raise BizError(ErrorCode.SOLUTION_NOT_FOUND)
        if solution.author_id != user.id:
            raise BizError(ErrorCode.FORBIDDEN, "仅方案作者可上传方案附件")
        if solution.status not in ("DRAFT", "SUBMITTED"):
            raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "已定稿的方案不可传附件")
        return "SOLUTION", biz_id
    # COMMENT
    from app.db.models import Comment
    comment = await db.get(Comment, biz_id)
    if comment is None or comment.demand_id != demand.id:
        raise BizError(ErrorCode.NOT_FOUND, "评论不存在")
    if comment.author_id != user.id:
        raise BizError(ErrorCode.FORBIDDEN, "仅评论作者可上传评论附件")
    return "COMMENT", biz_id


async def save_attachment(
    db, user, demand_id: int, filename: str | None, payload: bytes,
    biz_type: str = "DEMAND", biz_id: int | None = None,
) -> DemandAttachment:
    if biz_type not in BIZ_TYPES:
        raise BizError(ErrorCode.PARAM_INVALID, "附件类型无效")
    demand = (await db.execute(
        select(Demand).where(Demand.id == demand_id).with_for_update()
    )).scalar_one_or_none()
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
    biz_type, biz_id = await _resolve_biz_target(db, user, demand, biz_type, biz_id)
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
        biz_type=biz_type,
        biz_id=biz_id,
    )
    db.add(row)
    await db.flush()
    # AI 固定回执（不调模型）：上传动作写入会话上下文，模型只知文件名不知内容
    # 仅提报侧（草稿/待补充）注入；流转中交付物上传不打扰已关闭会话
    if demand.session_id is not None and demand.status in ("DRAFT", "NEED_INFO"):
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
    # 软删（文件本体保留，已流转附件可追溯）；删除权限=上传人或管理员，再按归属类型卡状态
    demand = await db.get(Demand, demand_id)
    if demand is None:
        raise BizError(ErrorCode.DEMAND_NOT_FOUND)
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
    if row.uploaded_by != user.id and not is_admin(user):
        raise BizError(ErrorCode.FORBIDDEN, "仅上传人或管理员可删除附件")
    if demand.status in ("DONE", "CLOSED"):
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "已办结的需求附件不可删除")
    if row.biz_type in ("DEMAND", "DRAFT"):
        # 提报侧附件：提交后不可删（P0 口径），保证受理方追溯
        if demand.status not in ("DRAFT", "NEED_INFO"):
            raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "草稿已提交或关闭，附件不可删除")
    elif row.biz_type == "SOLUTION":
        from app.db.models import Solution
        solution = await db.get(Solution, row.biz_id)
        if solution is None or solution.status != "DRAFT":
            raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅草稿方案的附件可删除")
    # COMMENT 附件：上传人或管理员可删（不再加状态限制）
    row.status = "DELETED"
    await db.flush()
