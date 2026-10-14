"""报表导出接口（蓝本 ReportController）。

export 建异步任务（EXECUTIVE/MANAGER，ADMIN 直通）；tasks 查本人任务；
download 下载 xlsx（本人或 ADMIN/EXECUTIVE，且任务 SUCCESS）。
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.core.deps import get_current_user, get_db, require_role
from app.core.result import ApiModel, ok
from app.services import report_service as service

router = APIRouter(prefix="/report")


class ExportBody(ApiModel):
    report_type: str = "DEMAND_LIST"
    params: dict[str, Any] = {}


@router.post("/export")
async def export(payload: ExportBody,
                 user=Depends(require_role("EXECUTIVE", "MANAGER")), db=Depends(get_db)):
    async with db.begin():
        task = await service.create_task(db, user, payload.report_type, payload.params)
        task_id, task_no = task.id, task.task_no
    service.schedule_execute(task_id)  # 提交后后台生成（asyncio 即发即忘先例）
    return ok({"id": task_id, "taskNo": task_no})


@router.get("/tasks")
async def tasks(current: int = Query(1, ge=1), size: int = Query(10, ge=1, le=100),
                user=Depends(get_current_user), db=Depends(get_db)):
    return ok(await service.page_mine(db, user, current=current, size=size))


@router.get("/download/{task_id}")
async def download(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
    task = await service.get_downloadable(db, user, task_id)
    # content-disposition 用 ASCII 文件名（中文名走 fileName 字段展示）
    return FileResponse(Path(task.file_path), media_type=
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        filename=f"{task.task_no}.xlsx")
