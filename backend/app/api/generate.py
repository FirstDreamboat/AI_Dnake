"""用例生成接口"""
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.generation_task import GenerationTask
from app.models.test_point import TestPoint
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.task import GenerateTaskCreate, GenerateTaskOut
from app.services import generate_service

router = APIRouter()


@router.get("/tasks")
def list_tasks(
    status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FR-任务持久化：分页查询任务历史（普通用户仅看自己的，管理员可看全部）"""
    user_id = None if user.role == "admin" else user.id
    tasks, total = generate_service.list_tasks(db, user_id, status, page, page_size)
    return ok(
        PageData(
            list=[GenerateTaskOut.model_validate(t) for t in tasks],
            total=total,
            page=page,
            page_size=page_size,
        )
    )


@router.post("/task/{task_id}/retry")
def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """FR-任务持久化：重试失败/取消/悬挂的任务"""
    task = generate_service.retry_task(db, task_id, user.id)
    return ok({"task_id": task.id, "task_no": task.task_no, "status": task.status}, "任务已重新加入队列")


@router.post("/task")
def create_task(
    req: GenerateTaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """发起用例生成任务"""
    task = generate_service.create_task(
        db, req.project_id, req.document_ids, req.options.model_dump(), user.id
    )
    # 启动后台执行
    generate_service.start_task(task.id, req.document_ids, req.options.model_dump(), user.id)
    return ok({"task_id": task.id, "task_no": task.task_no, "status": task.status}, "任务已创建")


@router.get("/task/{task_id}")
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = generate_service.get_task(db, task_id)
    return ok(task)


@router.get("/task/{task_id}/stream")
def task_stream(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE 实时推送任务进度"""
    from app.services import sse_service

    return StreamingResponse(
        sse_service.task_event_stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/task/{task_id}/cancel")
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = generate_service.cancel_task(db, task_id)
    return ok(task, "任务已取消")


@router.get("/task/{task_id}/summary")
def task_summary(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = generate_service.get_task(db, task_id)
    return ok(task.result_summary or {"total_case": task.total_case})


@router.get("/task/{task_id}/coverage")
def task_coverage(
    task_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """覆盖率分析：任务所属项目测试点的覆盖情况"""
    task = generate_service.get_task(db, task_id)
    points = db.scalars(
        select(TestPoint).where(TestPoint.project_id == task.project_id)
    ).all()
    from app.models.test_case import TestCase

    covered_ids = set(
        db.scalars(
            select(TestCase.test_point_id).where(
                TestCase.project_id == task.project_id, TestCase.test_point_id.isnot(None)
            )
        ).all()
    )
    items = [
        {
            "test_point_id": p.id,
            "name": p.name,
            "type": p.type,
            "covered": p.id in covered_ids,
            "case_count": 1 if p.id in covered_ids else 0,
        }
        for p in points
    ]
    total = len(items)
    covered = sum(1 for i in items if i["covered"])
    return ok(
        {
            "task_id": task_id,
            "total_points": total,
            "covered_points": covered,
            "coverage_rate": round(covered / total * 100, 1) if total else 0,
            "items": items,
        }
    )
