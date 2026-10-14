"""方案接口：撰写/编辑/提交评审/评审/列表/多版本对比/评审记录查询。

评审（review）限 MANAGER（ADMIN 直通）；其余登录可用，归属在服务层校验（作者/处理人/经理族）。
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from app.core.deps import get_current_user, get_db, require_role
from app.core.result import ApiModel, ok
from app.services import solution_service as service

router = APIRouter(prefix="/solution")


class SolutionSave(ApiModel):
    demand_id: int
    spec_content: str | None = Field(default=None, max_length=20000)
    solution_content: str | None = Field(default=None, max_length=20000)
    plan_delivery_at: date | None = None
    remark: str | None = Field(default=None, max_length=512)


class SolutionUpdate(ApiModel):
    spec_content: str | None = Field(default=None, max_length=20000)
    solution_content: str | None = Field(default=None, max_length=20000)
    plan_delivery_at: date | None = None
    remark: str | None = Field(default=None, max_length=512)


class ReviewBody(ApiModel):
    result: str = Field(pattern="^(PASS|REJECT)$")
    opinion: str | None = Field(default=None, max_length=2000)


@router.post("")
async def create(payload: SolutionSave, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        solution = await service.create(
            db, user, demand_id=payload.demand_id, spec_content=payload.spec_content,
            solution_content=payload.solution_content,
            plan_delivery_at=payload.plan_delivery_at, remark=payload.remark)
    return ok(service.serialize_solution(solution, user.name))


@router.put("/{solution_id}")
async def update(solution_id: int, payload: SolutionUpdate,
                 user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        solution = await service.update(
            db, user, solution_id, spec_content=payload.spec_content,
            solution_content=payload.solution_content,
            plan_delivery_at=payload.plan_delivery_at, remark=payload.remark)
    return ok(service.serialize_solution(solution, user.name))


@router.post("/{solution_id}/submit-review")
async def submit_review(solution_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    async with db.begin():
        solution = await service.submit_review(db, user, solution_id)
    return ok(service.serialize_solution(solution, user.name))


@router.post("/{solution_id}/review")
async def review(solution_id: int, payload: ReviewBody,
                 user=Depends(require_role("MANAGER")), db=Depends(get_db)):
    async with db.begin():
        solution = await service.review(db, user, solution_id,
                                        result=payload.result, opinion=payload.opinion)
    return ok(service.serialize_solution(solution, user.name))


@router.get("/list")
async def list_solutions(demand_id: int = Query(..., alias="demandId"),
                         user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.list_solutions(db, user, demand_id))


@router.get("/compare")
async def compare(demand_id: int = Query(..., alias="demandId"),
                  v1: int = Query(..., ge=1), v2: int = Query(..., ge=1),
                  user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.compare(db, user, demand_id, v1, v2))


@router.get("/reviews")
async def reviews(demand_id: int = Query(..., alias="demandId"),
                  review_type: str | None = Query(None, alias="reviewType"),
                  user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.list_reviews(db, user, demand_id, review_type))
