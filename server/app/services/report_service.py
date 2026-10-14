"""报表导出：report_export_task 异步任务（蓝本 ReportExportExecutor 口径）。

白话：经理点"导出报表"后系统后台慢慢生成 Excel，生成好发站内信，去任务列表下载。
- 状态机：PENDING → RUNNING → SUCCESS / FAILED（蓝本同口径；@Async 改 asyncio 即发即忘先例）
- task_no：RPT-YYYYMMDD-NNN（蓝本 Redis incr → 当日表内计数+1，同事务写入）
- 内容：13 列固定表头（需求编号/标题/类型/状态/紧急程度/提报人/提报组织/承接组织/处理人/
  提交时间/期望交付/关闭时间/交付周期小时）；上限 EXPORT_LIMIT=5000 行
- 查询条件：status/demandTypeCode/urgency/keyword（标题模糊）/submittedFrom-To/mine（只看自己提的）；
  一期 DataScope=全量（蓝本 ExportScope 数据范围快照留口）
- 存储：本地 report_dir（替代 MinIO），下载走 FileResponse，content-disposition 用 ASCII 文件名
- 成功站内信：REPORT_READY 模板渲染（模板缺失只记日志，不影响任务成功）
"""

import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import BizError, ErrorCode
from app.core.statemachine.engine import STATUS_LABELS
from app.db import session as db_session
from app.db.models import Demand, Notification, NotificationTemplate, ReportExportTask, User, now
from app.services import notification_service

logger = logging.getLogger(__name__)

REPORT_TYPES = {"DEMAND_LIST": "需求清单"}  # MONTHLY_REVIEW 预留
EXPORT_LIMIT = 5000
HEADERS = ["需求编号", "标题", "类型", "状态", "紧急程度", "提报人", "提报组织", "承接组织",
           "处理人", "提交时间", "期望交付", "关闭时间", "交付周期小时"]
REPORT_LINK = "/report"  # 前端报表任务页（hash 路由）


def _fmt_dt(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def _fmt_date(value: date | None) -> str:
    return value.isoformat() if value else ""


async def _next_task_no(db: AsyncSession) -> str:
    """RPT-YYYYMMDD-NNN：当日已有任务数+1（蓝本 Redis incr 语义，同事务内计数）。"""
    prefix = "RPT-" + now().strftime("%Y%m%d")
    count = (await db.execute(select(func.count(ReportExportTask.id)).where(
        ReportExportTask.task_no.like(f"{prefix}-%")))).scalar_one()
    return f"{prefix}-{count + 1:03d}"


async def create_task(db: AsyncSession, user: User, report_type: str, params: dict) -> ReportExportTask:
    """建 PENDING 任务（调用方持有事务）；提交后由 API 层 asyncio.create_task(execute)。"""
    if report_type not in REPORT_TYPES:
        raise BizError(ErrorCode.PARAM_INVALID, "报表类型仅支持 DEMAND_LIST")
    task = ReportExportTask(
        task_no=await _next_task_no(db), report_type=report_type,
        params_json=json.dumps(params, ensure_ascii=False), requester_id=user.id)
    db.add(task)
    await db.flush()
    return task


def _query_demands(params: dict, requester_id: int):
    """按导出参数拼查询（一期 DataScope=全量；mine=true 只看自己提的）。"""
    stmt = select(Demand)
    if params.get("status"):
        stmt = stmt.where(Demand.status == params["status"])
    if params.get("demandTypeCode"):
        stmt = stmt.where(Demand.demand_type_code == params["demandTypeCode"])
    if params.get("urgency"):
        stmt = stmt.where(Demand.urgency == params["urgency"])
    if params.get("keyword"):
        stmt = stmt.where(Demand.title.like(f"%{params['keyword']}%"))
    if params.get("submittedFrom"):
        stmt = stmt.where(Demand.submitted_at >= date.fromisoformat(params["submittedFrom"]))
    if params.get("submittedTo"):
        stmt = stmt.where(Demand.submitted_at < date.fromisoformat(params["submittedTo"]))
    if params.get("mine"):
        stmt = stmt.where(Demand.submitter_id == requester_id)
    return stmt.order_by(Demand.id.desc()).limit(EXPORT_LIMIT)


async def _render_rows(db: AsyncSession, demands: list[Demand]) -> list[list]:
    handler_ids = {d.assignee_id for d in demands if d.assignee_id}
    handlers = {}
    if handler_ids:
        users = (await db.execute(select(User).where(User.id.in_(handler_ids)))).scalars().all()
        handlers = {u.id: u.name for u in users}
    rows = []
    for d in demands:
        cycle_hours = ""
        if d.closed_at is not None and d.submitted_at is not None:
            cycle_hours = round((d.closed_at - d.submitted_at).total_seconds() / 3600, 1)
        rows.append([
            d.demand_no or "", d.title or "", d.demand_type_code or "",
            STATUS_LABELS.get(d.status, d.status), d.urgency or "",
            d.submitter_name or "", d.submitter_dept or "",
            "" if d.assignee_org_id is None else str(d.assignee_org_id),  # 一期 org 只建不用
            handlers.get(d.assignee_id, ""),
            _fmt_dt(d.submitted_at), _fmt_date(d.expect_delivery_at), _fmt_dt(d.closed_at),
            cycle_hours])
    return rows


async def _notify_ready(db: AsyncSession, task: ReportExportTask) -> None:
    """REPORT_READY 站内信（模板缺失只记日志，不影响任务成功）。"""
    template = (await db.execute(select(NotificationTemplate).where(
        NotificationTemplate.template_code == "REPORT_READY",
        NotificationTemplate.status == "ACTIVE"))).scalar_one_or_none()
    if template is None:
        logger.warning("REPORT_READY 模板缺失/停用，跳过通知 task=%s", task.task_no)
        return
    variables = {"report_name": REPORT_TYPES.get(task.report_type, task.report_type),
                 "task_no": task.task_no, "file_name": task.file_name or ""}
    db.add(Notification(
        demand_id=None, receiver_id=task.requester_id, channel="IN_APP",
        template_code="REPORT_READY",
        title=notification_service.render(template.title_template, variables),
        content=notification_service.render(template.content_template, variables),
        link=REPORT_LINK, send_status="SENT", sent_at=now()))


def _write_xlsx(task: ReportExportTask, rows: list[list]) -> Path:
    report_dir = Path(get_settings().report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{task.task_no}.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = REPORT_TYPES.get(task.report_type, task.report_type)
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    return path


async def execute(task_id: int) -> None:
    """后台执行：RUNNING → 查询生成 xlsx → SUCCESS + 站内信；异常 → FAILED + error_msg。"""
    factory = db_session.get_session_factory()  # 模块属性访问：测试 monkeypatch 受控 factory 生效
    async with factory() as db:
        try:
            async with db.begin():
                task = await db.get(ReportExportTask, task_id)
                if task is None or task.status != "PENDING":
                    return
                task.status = "RUNNING"
                params = json.loads(task.params_json or "{}")
                demands = (await db.execute(
                    _query_demands(params, task.requester_id))).scalars().all()
                rows = await _render_rows(db, demands)
            # 文件生成放事务外：IO 不占数据库连接；失败仅任务标记 FAILED
            path = _write_xlsx(task, rows)
            async with db.begin():
                task.status = "SUCCESS"
                task.file_path = str(path)
                task.file_name = f"{REPORT_TYPES.get(task.report_type, task.report_type)}-{task.task_no}.xlsx"
                task.finished_at = now()
                await _notify_ready(db, task)
        except Exception as exc:
            logger.warning("报表导出失败 task_id=%s", task_id, exc_info=True)
            async with db.begin():
                task = await db.get(ReportExportTask, task_id)
                if task is not None:
                    task.status = "FAILED"
                    task.error_msg = str(exc)[:500]
                    task.finished_at = now()


def schedule_execute(task_id: int) -> None:
    """即发即忘排队执行（overview.py 先例）。"""

    async def run():
        try:
            await execute(task_id)
        except Exception:
            logger.warning("报表后台任务异常 task_id=%s", task_id, exc_info=True)

    asyncio.create_task(run())


def serialize_task(task: ReportExportTask) -> dict:
    return {"id": task.id, "taskNo": task.task_no, "reportType": task.report_type,
            "status": task.status, "fileName": task.file_name, "errorMsg": task.error_msg,
            "createdAt": task.created_at, "finishedAt": task.finished_at}


async def page_mine(db: AsyncSession, user: User, *, current: int, size: int) -> dict:
    """本人导出任务分页（蓝本 GET /report/tasks：任何人看自己）。"""
    filters = [ReportExportTask.requester_id == user.id]
    total = (await db.execute(
        select(func.count(ReportExportTask.id)).where(*filters))).scalar_one()
    rows = (await db.execute(
        select(ReportExportTask).where(*filters)
        .order_by(ReportExportTask.id.desc())
        .offset((current - 1) * size).limit(size)
    )).scalars().all()
    return {"records": [serialize_task(row) for row in rows], "total": total,
            "size": size, "current": current, "pages": (total + size - 1) // size}


async def get_downloadable(db: AsyncSession, user: User, task_id: int) -> ReportExportTask:
    """下载鉴权（蓝本 requireDownloadable）：仅本人或 ADMIN/EXECUTIVE，且 status=SUCCESS。"""
    from app.core.deps import is_admin
    from app.services import role_service

    task = await db.get(ReportExportTask, task_id)
    if task is None:
        raise BizError(ErrorCode.NOT_FOUND, "导出任务不存在")
    if task.requester_id != user.id and not is_admin(user):
        roles = await role_service.effective_roles(db, user)
        if "EXECUTIVE" not in roles:
            raise BizError(ErrorCode.FORBIDDEN)
    if task.status != "SUCCESS" or not task.file_path:
        raise BizError(ErrorCode.CONFLICT, "报表尚未生成完成")
    return task
