from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import Field

from app.core.deps import get_current_user, get_db
from app.core.result import ApiModel, ok
from app.services import demand_service as service
from app.services.export import to_markdown

router = APIRouter(prefix="/demand")


class FormPayload(ApiModel):
    title: str | None = Field(default=None, max_length=256)
    demand_type_code: Literal["TECH", "MATL", "TRAIN"] | None = None
    content: str | None = Field(default=None, max_length=20000)
    urgency: Literal["NORMAL", "URGENT", "CRITICAL"] | None = None
    expect_delivery_at: str | None = None
    ext: dict[str, Any] | None = None
    field_sources: dict[str, Literal["default", "agent", "user"]] = Field(default_factory=dict)


class CreateDraft(FormPayload):
    client_request_id: str = Field(min_length=1, max_length=64)


class UpdateDraft(FormPayload):
    expected_revision: int = Field(ge=0)


class SubmitDraft(ApiModel):
    expected_revision: int = Field(ge=0)


class CloseDemand(ApiModel):
    reason: str = Field(min_length=1, max_length=256)


@router.post("")
async def create(payload: CreateDraft, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        demand = await service.create_draft(db, user, payload.model_dump(by_alias=True, exclude_unset=True))
    return ok(service.serialize_demand(demand))


@router.get("/my")
async def mine(page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100),
               status: Literal["DRAFT", "SUBMITTED", "CLOSED"] | None = None,
               user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.list_records(db, user, page=page, size=size, status=status))


@router.put("/{demand_id}")
async def update(demand_id: int, payload: UpdateDraft, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        demand = await service.update_draft(db, user, demand_id, payload.model_dump(by_alias=True, exclude_unset=True))
    return ok(service.serialize_demand(demand))


@router.post("/{demand_id}/submit")
async def submit(demand_id: int, payload: SubmitDraft, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        demand = await service.submit(db, user, demand_id, payload.expected_revision)
    return ok(service.serialize_demand(demand))


@router.post("/{demand_id}/close")
async def close(demand_id: int, payload: CloseDemand, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        demand = await service.close(db, user, demand_id, payload.reason)
    return ok(service.serialize_demand(demand))


@router.get("/{demand_id}/export.md")
async def export(demand_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    data = await service.detail(db, user, demand_id)
    filename = (data["demand"]["demandNo"] or f"draft-{demand_id}") + ".md"
    return Response(to_markdown(data["demand"], data["standard"], data["messages"]),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename)})


@router.get("/{demand_id}")
async def detail(demand_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.detail(db, user, demand_id))
