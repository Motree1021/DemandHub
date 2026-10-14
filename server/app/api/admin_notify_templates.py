"""通知模板管理接口（仅 ADMIN，蓝本 TemplateAdminController）：列表/新增/修改/删除/试渲染。"""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import Field

from app.core.deps import get_db, require_admin
from app.core.result import ApiModel, ok
from app.services import notification_service as service

router = APIRouter(prefix="/admin/notification-templates", dependencies=[Depends(require_admin)])


class TemplateSave(ApiModel):
    template_code: str = Field(min_length=1, max_length=64)
    template_name: str = Field(min_length=1, max_length=128)
    title_template: str = Field(min_length=1, max_length=256)
    content_template: str
    remark: str | None = Field(default=None, max_length=512)


class TemplateUpdate(ApiModel):
    template_name: str | None = Field(default=None, min_length=1, max_length=128)
    title_template: str | None = Field(default=None, min_length=1, max_length=256)
    content_template: str | None = None
    status: str | None = None
    remark: str | None = Field(default=None, max_length=512)


class TemplatePreview(ApiModel):
    template_code: str | None = None
    title_template: str | None = None
    content_template: str | None = None
    variables: dict[str, Any] = {}


@router.get("")
async def list_all(db=Depends(get_db)):
    return ok(await service.list_templates(db))


@router.post("")
async def create(payload: TemplateSave, db=Depends(get_db)):
    async with db.begin():
        row = await service.create_template(
            db, template_code=payload.template_code, template_name=payload.template_name,
            title_template=payload.title_template, content_template=payload.content_template,
            remark=payload.remark)
    return ok(service.serialize_template(row))


@router.put("/{template_id}")
async def update(template_id: int, payload: TemplateUpdate, db=Depends(get_db)):
    async with db.begin():
        row = await service.update_template(
            db, template_id, template_name=payload.template_name,
            title_template=payload.title_template, content_template=payload.content_template,
            status=payload.status, remark=payload.remark)
    return ok(service.serialize_template(row))


@router.delete("/{template_id}")
async def remove(template_id: int, db=Depends(get_db)):
    async with db.begin():
        await service.delete_template(db, template_id)
    return ok({"success": True})


@router.post("/preview")
async def preview(payload: TemplatePreview, db=Depends(get_db)):
    return ok(await service.preview_template(
        db, template_code=payload.template_code, title_template=payload.title_template,
        content_template=payload.content_template, variables=payload.variables))
