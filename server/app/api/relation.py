"""需求关系接口：增删查（PARENT/DEPENDS/DUPLICATE/SPLIT，双向可查）。"""

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_current_user, get_db
from app.core.result import ApiModel, ok
from app.services import relation_service as service

router = APIRouter(prefix="/relation")


class RelationAdd(ApiModel):
    demand_id: int
    related_demand_id: int
    relation_type: str = Field(pattern="^(PARENT|DEPENDS|DUPLICATE|SPLIT)$")


@router.post("")
async def add(payload: RelationAdd, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        await service.add(db, user, demand_id=payload.demand_id,
                          related_demand_id=payload.related_demand_id,
                          relation_type=payload.relation_type)
    return ok()


@router.delete("/{relation_id}")
async def delete(relation_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        await service.delete(db, user, relation_id)
    return ok()


@router.get("/list")
async def list_relations(demand_id: int = Query(..., alias="demandId"),
                         user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.list_relations(db, user, demand_id))
