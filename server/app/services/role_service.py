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
# REPORTER（提报人）：渠道建号默认角色，不参与任何角色守卫/状态机规则，天然最小权限
ROLE_CODES = ("ADMIN", "EXECUTIVE", "MANAGER", "HANDLER", "REPORTER")

# 需求类型权限（2026-10-16 拍板，按人统一配）：
# - 仅对业务角色生效；ADMIN 全类型直通（is_admin 口径），REPORTER 提报不受限
# - dh_user.type_scope 存逗号分隔类型码；NULL/空 = 无权限（严格口径，拍板不做存量补救）
TYPE_CODES = ("TECH", "MATL", "TRAIN")
TYPE_SCOPED_ROLES = ("EXECUTIVE", "MANAGER", "HANDLER")


def parse_type_scope(raw: str | None) -> list[str]:
    """type_scope 串 → 有序类型码列表（非法码静默丢弃，按 TYPE_CODES 顺序）。"""
    if not raw:
        return []
    given = {code.strip() for code in raw.split(",") if code.strip()}
    return [code for code in TYPE_CODES if code in given]


def user_type_codes(user: User) -> list[str] | None:
    """用户的可见类型集合：None = 不限制（ADMIN）；list = 有权类型（空 list = 无权限）。"""
    from app.core.deps import is_admin

    if is_admin(user):
        return None
    return parse_type_scope(user.type_scope)


def assert_type_allowed(user: User, type_code: str | None) -> None:
    """动作级拦截：类型不在权限范围 → 1126（ADMIN 直通）。"""
    codes = user_type_codes(user)
    if codes is not None and type_code not in codes:
        raise BizError(ErrorCode.TYPE_SCOPE_DENIED)


def type_scope_condition(user: User):
    """查询级过滤条件：ADMIN → None（不过滤）；有权限 → IN 条件；无权限 → 恒假（查不到）。"""
    from sqlalchemy import false

    from app.db.models import Demand

    codes = user_type_codes(user)
    if codes is None:
        return None
    if not codes:
        return false()
    return Demand.demand_type_code.in_(codes)


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


# ---- 用户管理多角色（/admin/users/{id}/roles）：主角色 + 兼任角色差量同步 ----
#
# 口径约定（2026-10-16 拍板，方案A：界面多选、底层复用）：
# - 主角色写 dh_user.role；兼任角色写「无范围无期限」授权行（org_id/scope/有效期全空）
# - 差量同步只管理这类空白授权行；授权管理里手工配的带范围/期限行不参与、绝不动
# - ADMIN 只能作主角色（is_admin 只认静态 role 与白名单，授权 ADMIN 进不了管理端）


def _blank_scope_grants(user_id: int):
    return select(DemandRoleGrant).where(
        DemandRoleGrant.user_id == user_id,
        DemandRoleGrant.is_deleted == 0,
        DemandRoleGrant.org_id.is_(None),
        DemandRoleGrant.demand_type_scope.is_(None),
        DemandRoleGrant.effective_from.is_(None),
        DemandRoleGrant.effective_to.is_(None),
    )


async def user_roles_map(db: AsyncSession, user_ids: list[int]) -> dict[int, list[str]]:
    """批量取「主角色 + 空白兼任授权角色」，按 ROLE_CODES 顺序排序（列表页防 N+1）。"""
    result: dict[int, list[str]] = {uid: [] for uid in user_ids}
    if not user_ids:
        return result
    users = (await db.execute(select(User.id, User.role).where(User.id.in_(user_ids)))).all()
    primary = {row.id: row.role for row in users}
    grants = (await db.execute(
        select(DemandRoleGrant.user_id, DemandRoleGrant.role_code)
        .where(DemandRoleGrant.user_id.in_(user_ids), DemandRoleGrant.is_deleted == 0,
               DemandRoleGrant.org_id.is_(None), DemandRoleGrant.demand_type_scope.is_(None),
               DemandRoleGrant.effective_from.is_(None), DemandRoleGrant.effective_to.is_(None))
    )).all()
    extras: dict[int, set[str]] = {uid: set() for uid in user_ids}
    for row in grants:
        extras[row.user_id].add(row.role_code)
    for uid in user_ids:
        effective = {primary.get(uid, "REPORTER"), *extras[uid]}
        result[uid] = [code for code in ROLE_CODES if code in effective]
    return result


async def sync_user_roles(
    db: AsyncSession, user: User, roles: list[str], types: list[str] | None = None,
    *, granted_by: int | None,
) -> list[str]:
    """多角色保存：主角色落 user.role，兼任角色差量同步空白授权行；返回保存后的有效角色。

    类型权限联动（按人统一配）：有效角色含业务角色（管理者/经理/处理人）时 types 必填，
    落 user.type_scope；不含业务角色时清空（管理员/提报人不需要，不留垃圾数据）。
    """
    user = await db.get(User, user.id)  # 归一到当前会话托管（调用方可能传入游离对象）
    unique = list(dict.fromkeys(roles))
    if not unique:
        raise BizError(ErrorCode.PARAM_INVALID, "至少保留一个角色")
    invalid = [code for code in unique if code not in ROLE_CODES]
    if invalid:
        raise BizError(ErrorCode.PARAM_INVALID, f"角色码仅允许 {'/'.join(ROLE_CODES)}")
    invalid_types = [code for code in (types or []) if code not in TYPE_CODES]
    if invalid_types:
        raise BizError(ErrorCode.PARAM_INVALID, f"需求类型仅允许 {'/'.join(TYPE_CODES)}")
    # ADMIN 只能作主角色：含 ADMIN 时强制主角色为 ADMIN
    if "ADMIN" in unique:
        user.role = "ADMIN"
    elif user.role not in unique:
        user.role = unique[0]
    concurrent = {code for code in unique if code != user.role}
    effective = {user.role, *concurrent}
    if any(code in TYPE_SCOPED_ROLES for code in effective):
        ordered = [code for code in TYPE_CODES if code in set(types or [])]
        if not ordered:
            raise BizError(ErrorCode.PARAM_INVALID, "业务角色需选择至少一个需求类型权限")
        user.type_scope = ",".join(ordered)
    else:
        user.type_scope = None
    user.updated_at = now()
    rows = (await db.execute(_blank_scope_grants(user.id))).scalars().all()
    existing = {row.role_code: row for row in rows}
    for code in concurrent - set(existing):  # 缺的新增
        db.add(DemandRoleGrant(user_id=user.id, role_code=code, granted_by=granted_by))
    for code, row in existing.items():  # 多的回收（软删口径同 delete_grant）
        if code not in concurrent:
            row.is_deleted = row.id
            row.updated_at = now()
    await db.flush()
    return [code for code in ROLE_CODES if code in {user.role, *concurrent}]
