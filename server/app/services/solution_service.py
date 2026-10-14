"""方案服务：撰写（草稿）→ 提交评审 → 评审联动需求状态；多版本对比；评审留痕不可改。

评审联动（蓝本口径）：PASS 且 plan_delivery_at 非空 → 写 demand.expect_delivery_at；
PASS 写 demand.confirmed_at；REJECT 意见必填。同一需求同一时刻仅允许一个在评方案。
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.core.statemachine import engine
from app.db.models import Review, Solution, User, now
from app.services.flow_service import get_viewable, require_assignee_or_privileged


async def _get_solution(db: AsyncSession, solution_id: int) -> Solution:
    solution = await db.get(Solution, solution_id)
    if solution is None:
        raise BizError(ErrorCode.SOLUTION_NOT_FOUND)
    return solution


async def _require_solution_operator(db: AsyncSession, user: User, demand) -> None:
    """方案撰写/提评归属：当前处理人本人，或经理族代办 / ADMIN。"""
    from app.services import role_service

    roles = await role_service.effective_roles(db, user)
    require_assignee_or_privileged(user, demand, roles, "仅当前处理人或经理/管理员可操作方案")


def serialize_solution(solution: Solution, author_name: str | None = None) -> dict:
    from app.core.result import encode

    return {
        "id": solution.id, "demandId": solution.demand_id, "version": solution.version,
        "authorId": solution.author_id, "authorName": author_name,
        "specContent": solution.spec_content, "solutionContent": solution.solution_content,
        "planDeliveryAt": encode(solution.plan_delivery_at), "status": solution.status,
        "remark": solution.remark,
        "createdAt": encode(solution.created_at), "updatedAt": encode(solution.updated_at),
    }


async def create(
    db: AsyncSession, user: User, *,
    demand_id: int, spec_content: str | None, solution_content: str | None,
    plan_delivery_at: date | None, remark: str | None,
) -> Solution:
    demand = await get_viewable(db, user, demand_id)
    if demand.status != "ANALYZING":
        raise BizError(ErrorCode.ILLEGAL_STATE_TRANSITION, "仅分析中可撰写方案")
    await _require_solution_operator(db, user, demand)
    max_version = (await db.execute(
        select(func.max(Solution.version)).where(Solution.demand_id == demand_id)
    )).scalar_one() or 0
    solution = Solution(
        demand_id=demand_id, version=max_version + 1, author_id=user.id,
        spec_content=spec_content, solution_content=solution_content,
        plan_delivery_at=plan_delivery_at, remark=remark,
    )
    db.add(solution)
    await db.flush()
    return solution


async def update(
    db: AsyncSession, user: User, solution_id: int, *,
    spec_content: str | None, solution_content: str | None,
    plan_delivery_at: date | None, remark: str | None,
) -> Solution:
    solution = await _get_solution(db, solution_id)
    if solution.status != "DRAFT":
        raise BizError(ErrorCode.BIZ_ERROR, "仅草稿状态的方案可编辑")
    if solution.author_id != user.id:
        raise BizError(ErrorCode.FORBIDDEN, "仅方案作者可编辑")
    solution.spec_content = spec_content
    solution.solution_content = solution_content
    solution.plan_delivery_at = plan_delivery_at
    solution.remark = remark
    solution.updated_at = now()
    await db.flush()
    return solution


async def submit_review(db: AsyncSession, user: User, solution_id: int) -> Solution:
    solution = await _get_solution(db, solution_id)
    demand = await get_viewable(db, user, solution.demand_id)
    await _require_solution_operator(db, user, demand)
    if solution.status not in {"DRAFT", "REJECTED"}:
        raise BizError(ErrorCode.BIZ_ERROR, "仅草稿或已打回的方案可提交评审")
    reviewing = (await db.execute(select(func.count(Solution.id)).where(
        Solution.demand_id == solution.demand_id, Solution.status == "SUBMITTED",
        Solution.id != solution.id,
    ))).scalar_one()
    if reviewing > 0:
        raise BizError(ErrorCode.BIZ_ERROR, "已有方案在评审中，请先完成评审")
    await engine.transition(
        db, solution.demand_id, "SUBMIT_REVIEW", user,
        extra={"solutionId": solution.id, "version": solution.version},
    )
    solution.status = "SUBMITTED"
    solution.updated_at = now()
    await db.flush()
    return solution


async def review(
    db: AsyncSession, user: User, solution_id: int, *, result: str, opinion: str | None,
) -> Solution:
    """方案评审（MANAGER/ADMIN）：PASS → 需求 CONFIRMED + 方案 APPROVED；REJECT → ANALYZING + REJECTED。"""
    if result not in {"PASS", "REJECT"}:
        raise BizError(ErrorCode.PARAM_INVALID, "评审结论必须为 PASS 或 REJECT")
    solution = await _get_solution(db, solution_id)
    demand = await get_viewable(db, user, solution.demand_id)
    if solution.status != "SUBMITTED":
        raise BizError(ErrorCode.BIZ_ERROR, "该方案不在评审中")
    if result == "PASS":
        updates: dict = {"confirmed_at": now()}
        if solution.plan_delivery_at is not None:  # 评审联动字段
            updates["expect_delivery_at"] = solution.plan_delivery_at
        await engine.transition(db, demand.id, "REVIEW_PASS", user, comment=opinion, field_update=updates)
        solution.status = "APPROVED"
    else:
        if not opinion or not opinion.strip():
            raise BizError(ErrorCode.PARAM_INVALID, "打回意见必填")
        opinion = opinion.strip()
        await engine.transition(db, demand.id, "REVIEW_REJECT", user, comment=opinion)
        solution.status = "REJECTED"
    solution.updated_at = now()
    db.add(Review(
        demand_id=demand.id, review_type="SOLUTION", target_id=solution.id,
        result=result, opinion=opinion, reviewer_id=user.id,
    ))
    await db.flush()
    return solution


async def list_solutions(db: AsyncSession, user: User, demand_id: int) -> list[dict]:
    await get_viewable(db, user, demand_id)
    rows = (await db.execute(
        select(Solution, User.name)
        .join(User, Solution.author_id == User.id)
        .where(Solution.demand_id == demand_id)
        .order_by(Solution.version)
    )).all()
    return [serialize_solution(s, name) for s, name in rows]


async def compare(db: AsyncSession, user: User, demand_id: int, v1: int, v2: int) -> dict:
    """多版本对比：返回两个版本完整内容，前端做 diff。"""
    await get_viewable(db, user, demand_id)
    rows = (await db.execute(
        select(Solution, User.name)
        .join(User, Solution.author_id == User.id)
        .where(Solution.demand_id == demand_id, Solution.version.in_([v1, v2]))
        .order_by(Solution.version)
    )).all()
    if len(rows) < 2:
        raise BizError(ErrorCode.SOLUTION_NOT_FOUND, "对比的版本不存在")
    return {"items": [serialize_solution(s, name) for s, name in rows]}


async def list_reviews(
    db: AsyncSession, user: User, demand_id: int, review_type: str | None,
) -> list[dict]:
    from app.core.result import encode

    await get_viewable(db, user, demand_id)
    filters = [Review.demand_id == demand_id]
    if review_type:
        filters.append(Review.review_type == review_type)
    rows = (await db.execute(
        select(Review, User.name)
        .join(User, Review.reviewer_id == User.id)
        .where(*filters).order_by(Review.id)
    )).all()
    return [{
        "id": r.id, "demandId": r.demand_id, "reviewType": r.review_type,
        "targetId": r.target_id, "result": r.result, "opinion": r.opinion,
        "qualityScore": r.quality_score, "satisfactionScore": r.satisfaction_score,
        "reviewerId": r.reviewer_id, "reviewerName": name, "createdAt": encode(r.created_at),
    } for r, name in rows]


async def latest_submitted(db: AsyncSession, demand_id: int) -> Solution | None:
    return (await db.execute(
        select(Solution).where(Solution.demand_id == demand_id, Solution.status == "SUBMITTED")
        .order_by(Solution.version.desc()).limit(1)
    )).scalar_one_or_none()
