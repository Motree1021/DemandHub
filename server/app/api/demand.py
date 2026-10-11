import mimetypes
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import Field, field_validator

from app.agent.overview import schedule_overview_rewrite
from app.core.deps import get_current_user, get_db
from app.core.errors import BizError, ErrorCode
from app.core.result import ApiModel, ok
from app.services import attachment_service
from app.services import demand_service as service
from app.services.attachment_service import MAX_SIZE
from app.services.export import to_markdown

router = APIRouter(prefix="/demand")


class FormPayload(ApiModel):
    title: str | None = Field(default=None, max_length=256)
    demand_type_code: Literal["TECH", "MATL", "TRAIN"] | None = None
    content: str | None = Field(default=None, max_length=20000)
    urgency: Literal["NORMAL", "URGENT", "CRITICAL"] | None = None
    expect_delivery_at: str | None = None
    ext: dict[str, Any] | None = None
    elements: dict[str, dict[str, Any]] | None = None
    field_sources: dict[str, Literal["default", "agent", "user"]] = Field(default_factory=dict)

    @field_validator("urgency", "demand_type_code", mode="before")
    @classmethod
    def blank_literal_to_none(cls, value):
        # H5 表单空值惯用空字符串（newForm urgency: ''）；Literal 字段须在 schema 层归一为 None，
        # 交给 filter_form 的 blank 容错，否则空串被 Literal 校验 422 拦截
        return None if value == "" else value


class CreateDraft(FormPayload):
    client_request_id: str = Field(min_length=1, max_length=64)


class UpdateDraft(FormPayload):
    expected_revision: int = Field(ge=0)
    # 手工改要素保存后往提报会话写一条播报消息（FR-06）；AI 链路与其余保存不带此标志
    notify_changes: bool = False


class SubmitDraft(ApiModel):
    expected_revision: int = Field(ge=0)


class CloseDemand(ApiModel):
    reason: str = Field(min_length=1, max_length=256)


class ChangeMode(ApiModel):
    expected_revision: int = Field(ge=0)
    level: Literal["light", "standard"]


@router.post("")
async def create(payload: CreateDraft, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        demand = await service.create_draft(
            db, user, payload.model_dump(by_alias=True, exclude_unset=True)
        )
        result = await service.serialize_with_logs(db, demand)
    return ok(result)


@router.get("/my")
async def mine(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Literal["DRAFT", "SUBMITTED", "NEED_INFO", "CLOSED"] | None = None,
    user=Depends(get_current_user),
    db=Depends(get_db),
):
    return ok(await service.list_records(db, user, page=page, size=size, status=status))


@router.put("/{demand_id}")
async def update(
    demand_id: int, payload: UpdateDraft, user=Depends(get_current_user), db=Depends(get_db)
):
    async with db.begin():
        demand = await service.update_draft(
            db, user, demand_id, payload.model_dump(by_alias=True, exclude_unset=True)
        )
        result = await service.serialize_with_logs(db, demand)
    # 手工改要素保存后：后台异步重写需求概述（失败静默，保存已完成的响应不受影响）
    if payload.notify_changes:
        schedule_overview_rewrite(demand.id, user.id)
    return ok(result)


@router.post("/{demand_id}/submit")
async def submit(
    demand_id: int, payload: SubmitDraft, user=Depends(get_current_user), db=Depends(get_db)
):
    async with db.begin():
        demand = await service.submit(db, user, demand_id, payload.expected_revision)
        result = await service.serialize_with_logs(db, demand)
    return ok(result)


@router.post("/{demand_id}/close")
async def close(
    demand_id: int, payload: CloseDemand, user=Depends(get_current_user), db=Depends(get_db)
):
    async with db.begin():
        demand = await service.close(db, user, demand_id, payload.reason)
        result = await service.serialize_with_logs(db, demand)
    return ok(result)


# 提报口径改判（2026-10-11 方案④）：轻量↔常规双向，打回补充期间禁降轻量；响应同 PUT /demand 便于前端 applyDemand 刷新
@router.post("/{demand_id}/mode")
async def change_mode(
    demand_id: int, payload: ChangeMode, user=Depends(get_current_user), db=Depends(get_db)
):
    async with db.begin():
        demand = await service.change_mode(db, user, demand_id, payload.expected_revision, payload.level)
        result = await service.serialize_with_logs(db, demand)
    return ok(result)


@router.get("/{demand_id}/export.md")
async def export(demand_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    data = await service.detail(db, user, demand_id)
    filename = (data["demand"]["demandNo"] or f"draft-{demand_id}") + ".md"
    return Response(
        to_markdown(data["demand"], data["standard"], data["messages"], data["attachments"]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)},
    )


@router.get("/{demand_id}")
async def detail(demand_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.detail(db, user, demand_id))


# ---- 需求附件（图片/文档）：仅 DRAFT 可传删；查看/下载与需求详情同口径（本人或 ADMIN）----


@router.post("/{demand_id}/attachments")
async def upload_attachment(
    demand_id: int, file: UploadFile = File(...), user=Depends(get_current_user), db=Depends(get_db)
):
    # 读取上限+1 字节：超大文件不必整份载入内存即可拒绝
    payload = await file.read(MAX_SIZE + 1)
    async with db.begin():
        row = await attachment_service.save_attachment(db, user, demand_id, file.filename, payload)
    return ok(attachment_service.serialize_attachment(row))


@router.get("/{demand_id}/attachments")
async def list_attachments(demand_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    await attachment_service.viewable_demand(db, user, demand_id)
    return ok(await attachment_service.serialize_list(db, demand_id))


@router.get("/{demand_id}/attachments/{attachment_id}/download")
async def download_attachment(
    demand_id: int, attachment_id: int, user=Depends(get_current_user), db=Depends(get_db)
):
    _, row = await attachment_service.get_attachment(db, user, demand_id, attachment_id)
    path = attachment_service.storage_path(demand_id, row.storage_key, row.file_ext)
    if not path.is_file():
        raise BizError(ErrorCode.NOT_FOUND, "附件文件已失效")
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(row.file_name)[0] or "application/octet-stream",
        filename=row.file_name,
    )


@router.delete("/{demand_id}/attachments/{attachment_id}")
async def delete_attachment(
    demand_id: int, attachment_id: int, user=Depends(get_current_user), db=Depends(get_db)
):
    async with db.begin():
        await attachment_service.delete_attachment(db, user, demand_id, attachment_id)
    return ok()
