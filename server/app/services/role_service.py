"""业务角色解析与本地授权（demand_role_grant）管理。

白话：一个人能扮演什么角色 = 账号上的静态角色（dh_user.role）
      ∪ 授权表里当前生效的授权行（role_code）的并集（决策③口径）。
- 授权有效期：effective_from/to 留空 = 不限；到点自动生效/失效，无需人工干预
- 软删除：回收授权不删行，is_deleted 置成行 id（唯一键含该列，反复授权/回收不撞键）
- 一期简化：org_id / demand_type_scope 只存不参与过滤（DataScope=全量，与现有列表口径一致）
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import DemandRoleGrant, User, now

# 与状态机 engine.VALID_ROLES 同集合；单独持有避免 core→services 反向依赖
ROLE_CODES = ("ADMIN", "EXECUTIVE", "MANAGER", "HANDLER")


async def effective_role_codes(db: AsyncSession, user_id: int) -> set[str]:
    """用户当前生效的授权角色码（不含静态 role）。"""
    current = now()
    rows = (await db.execute(
        select(DemandRoleGrant.role_code).where(
            DemandRoleGrant.user_id == user_id,
            DemandRoleGrant.is_deleted == 0,
            or_(DemandRoleGrant.effective_from.is_(None), DemandRoleGrant.effective_from <= current),
            or_(DemandRoleGrant.effective_to.is_(None), DemandRoleGrant.effective_to >= current),
        )
    )).scalars().all()
    return set(rows)


async def effective_roles(db: AsyncSession, user: User) -> frozenset[str]:
    """有效角色 = 静态 role ∪ 生效授权 role_code。"""
    codes = await effective_role_codes(db, user.id)
    codes.add(user.role)
    return frozenset(codes)


def is_manager_like(roles: frozenset[str] | set[str]) -> bool:
    """经理族判定（蓝本 isManagerLike 含 ADMIN）：可代办处理人动作。"""
    return "MANAGER" in roles or "ADMIN" in roles


# ---- 授权管理（仅 ADMIN，见 api/admin_grants.py） ----


def serialize_grant(grant: DemandRoleGrant) -> dict:
    return {
        "id": grant.id,
        "userId": grant.user_id,
        "roleCode": grant.role_code,
        "orgId": grant.org_id,
        "demandTypeScope": grant.demand_type_scope,
        "effectiveFrom": grant.effective_from,
        "effectiveTo": grant.effective_to,
        "grantedBy": grant.granted_by,
        "createdAt": grant.created_at,
        "updatedAt": grant.updated_at,
    }


async def page_grants(
    db: AsyncSession, *, user_id: int | None, role_code: str | None, page: int, size: int,
) -> tuple[list[DemandRoleGrant], int]:
    filters = [DemandRoleGrant.is_deleted == 0]
    if user_id is not None:
        filters.append(DemandRoleGrant.user_id == user_id)
    if role_code:
        filters.append(DemandRoleGrant.role_code == role_code)
    total = (await db.execute(
        select(func.count(DemandRoleGrant.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(DemandRoleGrant).where(*filters)
        .order_by(DemandRoleGrant.id.desc())
        .offset((page - 1) * size).limit(size)
    )).scalars().all()
    return list(rows), total


def _validate_payload(
    role_code: str, effective_from: datetime | None, effective_to: datetime | None,
) -> None:
    if role_code not in ROLE_CODES:
        raise BizError(ErrorCode.PARAM_INVALID, f"角色码仅允许 {'/'.join(ROLE_CODES)}")
    if effective_from and effective_to and effective_from > effective_to:
        raise BizError(ErrorCode.PARAM_INVALID, "生效开始时间不能晚于截止时间")


async def _ensure_not_duplicated(
    db: AsyncSession, *, user_id: int, role_code: str, org_id: int | None,
    demand_type_scope: str | None, exclude_id: int | None,
) -> None:
    """同人同角色同范围（组织+类型集合）授权唯一（蓝本 ensureNotDuplicated，仅未删除行）。"""
    filters = [
        DemandRoleGrant.user_id == user_id,
        DemandRoleGrant.role_code == role_code,
        DemandRoleGrant.is_deleted == 0,
    ]
    if exclude_id is not None:
        filters.append(DemandRoleGrant.id != exclude_id)
    if org_id is None:
        filters.append(DemandRoleGrant.org_id.is_(None))
    else:
        filters.append(DemandRoleGrant.org_id == org_id)
    if demand_type_scope is None:
        filters.append(DemandRoleGrant.demand_type_scope.is_(None))
    else:
        filters.append(DemandRoleGrant.demand_type_scope == demand_type_scope)
    count = (await db.execute(
        select(func.count(DemandRoleGrant.id)).where(*filters))).scalar_one()
    if count > 0:
        raise BizError(ErrorCode.ROLE_GRANT_DUPLICATED)


async def create_grant(
    db: AsyncSession, *, user_id: int, role_code: str, org_id: int | None,
    demand_type_scope: str | None, effective_from: datetime | None,
    effective_to: datetime | None, granted_by: int | None,
) -> DemandRoleGrant:
    if await db.get(User, user_id) is None:
        raise BizError(ErrorCode.USER_NOT_FOUND)
    scope = demand_type_scope.strip() if demand_type_scope else None
    _validate_payload(role_code, effective_from, effective_to)
    await _ensure_not_duplicated(
        db, user_id=user_id, role_code=role_code, org_id=org_id,
        demand_type_scope=scope, exclude_id=None)
    grant = DemandRoleGrant(
        user_id=user_id, role_code=role_code, org_id=org_id, demand_type_scope=scope,
        effective_from=effective_from, effective_to=effective_to, granted_by=granted_by)
    db.add(grant)
    await db.flush()
    return grant


async def update_grant(
    db: AsyncSession, grant_id: int, *, user_id: int, role_code: str, org_id: int | None,
    demand_type_scope: str | None, effective_from: datetime | None, effective_to: datetime | None,
) -> DemandRoleGrant:
    grant = await db.get(DemandRoleGrant, grant_id)
    if grant is None or grant.is_deleted != 0:
        raise BizError(ErrorCode.ROLE_GRANT_NOT_FOUND)
    if await db.get(User, user_id) is None:
        raise BizError(ErrorCode.USER_NOT_FOUND)
    scope = demand_type_scope.strip() if demand_type_scope else None
    _validate_payload(role_code, effective_from, effective_to)
    await _ensure_not_duplicated(
        db, user_id=user_id, role_code=role_code, org_id=org_id,
        demand_type_scope=scope, exclude_id=grant_id)
    grant.user_id = user_id
    grant.role_code = role_code
    grant.org_id = org_id
    grant.demand_type_scope = scope
    grant.effective_from = effective_from
    grant.effective_to = effective_to
    grant.updated_at = now()
    await db.flush()
    return grant


async def delete_grant(db: AsyncSession, grant_id: int) -> None:
    """回收授权：is_deleted 置成行 id（蓝本口径，唯一键含该列，可反复授权/回收）。"""
    grant = await db.get(DemandRoleGrant, grant_id)
    if grant is None or grant.is_deleted != 0:
        raise BizError(ErrorCode.ROLE_GRANT_NOT_FOUND)
    grant.is_deleted = grant.id
    grant.updated_at = now()
    await db.flush()
