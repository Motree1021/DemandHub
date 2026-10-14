"""组织树服务（蓝本 OrgAdminService）：物化路径树 CRUD + 删除校验 + demand 两列回填解析。

白话：组织树就是公司的部门架构。每个组织记一条「路径」（如 /100/110/），
查某部门及其下级时按路径前缀匹配即可，不用递归查库。
- path 物化路径尾斜杠：新增先占位插入拿 id 再回填 path；移动整树前缀替换
- 删除五校验：根/900 虚拟组织/有子组织/授权引用/需求引用（用户主组织未建列，用户引用不做）
- 提报人组织解析：user.dept_id → external_dept_id 命中，未命中挂外部虚拟组织 900（蓝本口径）
- 承接组织路由：assignee_org_id = demand_type.default_org_id（类型修正时随新类型重路由）"""

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import BizError, ErrorCode
from app.db.models import Demand, DemandOrg, DemandRoleGrant, DemandType, User

EXTERNAL_ORG_ID = 900  # 外部虚拟组织（渠道部门未命中的兜底挂载点，种子保证存在）
LEVELS = ("LINE", "DEPT", "GROUP")
ORG_KINDS = ("REPORTER", "ASSIGNER", "BOTH")
STATUSES = ("ACTIVE", "DISABLED")


def serialize_org(row: DemandOrg) -> dict:
    return {
        "orgId": row.id,
        "name": row.name,
        "level": row.level,
        "parentId": row.parent_id,
        "path": row.path,
        "orgKind": row.org_kind,
        "externalDeptId": row.external_dept_id,
        "status": row.status,
    }


def build_tree(rows: list[DemandOrg]) -> list[dict]:
    """平铺行 → 嵌套树（children）；父缺失的节点挂到根层防丢。"""
    nodes = {row.id: {**serialize_org(row), "children": []} for row in rows}
    roots = []
    for row in rows:
        node = nodes[row.id]
        parent = nodes.get(row.parent_id)
        (parent["children"] if parent else roots).append(node)
    return roots


async def list_orgs(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(DemandOrg).order_by(DemandOrg.id))).scalars().all()
    return [serialize_org(row) for row in rows]


async def tree(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(DemandOrg).order_by(DemandOrg.id))).scalars().all()
    return build_tree(rows)


async def _get(db: AsyncSession, org_id: int) -> DemandOrg:
    row = (await db.execute(select(DemandOrg).where(DemandOrg.id == org_id))).scalar_one_or_none()
    if row is None:
        raise BizError(ErrorCode.NOT_FOUND, "组织不存在")
    return row


def _check_fields(name: str | None, level: str | None, org_kind: str | None,
                  status: str | None) -> None:
    if name is not None and not name.strip():
        raise BizError(ErrorCode.PARAM_INVALID, "组织名称必填")
    if level is not None and level not in LEVELS:
        raise BizError(ErrorCode.PARAM_INVALID, f"层级仅允许 {'/'.join(LEVELS)}")
    if org_kind is not None and org_kind not in ORG_KINDS:
        raise BizError(ErrorCode.PARAM_INVALID, f"组织类型仅允许 {'/'.join(ORG_KINDS)}")
    if status is not None and status not in STATUSES:
        raise BizError(ErrorCode.PARAM_INVALID, f"状态仅允许 {'/'.join(STATUSES)}")


async def create_org(db: AsyncSession, *, name: str, level: str, parent_id: int,
                     org_kind: str, external_dept_id: str | None = None) -> DemandOrg:
    _check_fields(name, level, org_kind, None)
    parent = await _get(db, parent_id)  # 根之下才可挂新组织（parent_id=0 无行 → 404）
    row = DemandOrg(name=name.strip(), level=level, parent_id=parent_id,
                    path=parent.path + "0/",  # 占位路径：先拿自增 id 再回填
                    org_kind=org_kind, external_dept_id=external_dept_id, status="ACTIVE")
    db.add(row)
    await db.flush()
    row.path = f"{parent.path}{row.id}/"
    await db.flush()
    return row


async def update_org(db: AsyncSession, org_id: int, *, name: str | None = None,
                     level: str | None = None, parent_id: int | None = None,
                     org_kind: str | None = None, external_dept_id: str | None = None,
                     status: str | None = None) -> DemandOrg:
    """parent_id 变更 = 移动：自身路径重算 + 整棵子树路径前缀替换；禁止移到自己的子树下（防环）。"""
    row = await _get(db, org_id)
    _check_fields(name, level, org_kind, status)
    if parent_id is not None and parent_id != row.parent_id:
        new_parent = await _get(db, parent_id)
        if new_parent.path.startswith(row.path):
            raise BizError(ErrorCode.PARAM_INVALID, "不能移动到自己的子组织下")
        old_prefix, new_prefix = row.path, f"{new_parent.path}{row.id}/"
        # 整树前缀替换（子树 startsWith 旧前缀的全部后代）
        await db.execute(
            update(DemandOrg)
            .where(DemandOrg.path.startswith(old_prefix), DemandOrg.id != row.id)
            .values(path=func.concat(new_prefix, func.substring(DemandOrg.path, len(old_prefix) + 1))))
        row.path, row.parent_id = new_prefix, parent_id
    if name is not None:
        row.name = name.strip()
    if level is not None:
        row.level = level
    if org_kind is not None:
        row.org_kind = org_kind
    if external_dept_id is not None:
        row.external_dept_id = external_dept_id or None
    if status is not None:
        row.status = status
    await db.flush()
    return row


async def delete_org(db: AsyncSession, org_id: int) -> None:
    row = await _get(db, org_id)
    if row.parent_id == 0:
        raise BizError(ErrorCode.BIZ_ERROR, "根组织不可删除")
    if row.id == EXTERNAL_ORG_ID:
        raise BizError(ErrorCode.BIZ_ERROR, "外部虚拟组织不可删除")
    children = (await db.execute(
        select(func.count(DemandOrg.id)).where(DemandOrg.parent_id == org_id))).scalar_one()
    if children:
        raise BizError(ErrorCode.BIZ_ERROR, "存在子组织，不可删除")
    grants = (await db.execute(
        select(func.count(DemandRoleGrant.id)).where(
            DemandRoleGrant.org_id == org_id, DemandRoleGrant.is_deleted == 0))).scalar_one()
    if grants:
        raise BizError(ErrorCode.BIZ_ERROR, "存在授权引用，不可删除")
    demands = (await db.execute(
        select(func.count(Demand.id)).where(
            or_(Demand.assignee_org_id == org_id, Demand.submitter_org_id == org_id)))).scalar_one()
    if demands:
        raise BizError(ErrorCode.BIZ_ERROR, "存在需求引用，不可删除")
    await db.delete(row)
    await db.flush()


# ---- demand 两列回填解析 ----

async def resolve_user_org_id(db: AsyncSession, user: User) -> int:
    """提报人组织：dept_id → external_dept_id 命中；未命中挂外部虚拟组织 900（蓝本口径）。"""
    if user.dept_id:
        org_id = (await db.execute(
            select(DemandOrg.id).where(DemandOrg.external_dept_id == user.dept_id))
        ).scalar_one_or_none()
        if org_id is not None:
            return org_id
    return EXTERNAL_ORG_ID


async def resolve_type_org_id(db: AsyncSession, type_code: str | None) -> int | None:
    """承接组织路由：类型的默认承接组织；类型未注册（yaml 兜底类型）则 None=管理者队列。"""
    if not type_code:
        return None
    return (await db.execute(
        select(DemandType.default_org_id).where(DemandType.type_code == type_code))
    ).scalar_one_or_none()
