"""用例生成任务服务

任务创建后进入 pending，由后台线程执行智能体工作流，
进度通过 task 表 progress 字段持久化，前端通过 SSE/轮询获取。
"""
import threading
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.agents.workflow import GenerateWorkflow
from app.core.exceptions import BusinessError, NotFoundError
from app.database import SessionLocal
from app.models.document import Document
from app.models.generation_task import GenerationTask
from app.models.test_point import TestPoint
from app.services.document_service import parse_document
from app.services.test_case_service import save_generated_case


def _gen_task_no() -> str:
    return f"GEN-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:4].upper()}"


def create_task(db: Session, project_id: int, document_ids: list[int], options: dict, user_id: int) -> GenerationTask:
    """创建生成任务（document_ids 一并写入 options 以支持重试/重启恢复）"""
    task = GenerationTask(
        task_no=_gen_task_no(),
        project_id=project_id,
        document_id=document_ids[0],
        created_by=user_id,
        status="pending",
        progress=0,
        options={**(options or {}), "document_ids": document_ids},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _notify_task_done(db: Session, task: GenerationTask, user_id: int) -> None:
    """任务完成/失败后发送站内通知"""
    user = db.get(User, user_id)
    if not user:
        return
    if task.status == "success":
        notification_service.create_notification(
            db,
            user_id,
            category="task",
            title="用例生成任务完成",
            content=f"任务 {task.task_no} 已成功生成 {task.total_case} 条用例",
            related_id=task.id,
        )
    elif task.status == "failed":
        notification_service.create_notification(
            db,
            user_id,
            category="task",
            title="用例生成任务失败",
            content=f"任务 {task.task_no} 生成失败：{task.error_msg or '未知错误'}",
            related_id=task.id,
        )


def _run_workflow(task_id: int, document_ids: list[int], options: dict, user_id: int) -> None:
    """后台执行工作流（独立数据库会话）"""
    db = SessionLocal()
    try:
        task = db.get(GenerationTask, task_id)
        if not task:
            return
        task.status = "running"
        task.started_at = datetime.now()
        db.commit()

        # 解析所有关联文档
        contents: list[str] = []
        for doc_id in document_ids:
            doc, text = parse_document(db, doc_id)
            if text:
                contents.append(f"【文档：{doc.title}】\n{text}")

        total_case = 0
        generated_cases: list[dict] = []
        reviews: list[dict] = []
        business_flows: list[dict] = []
        error_msg = None

        def progress_cb(percent: int, stage: str):
            task = db.get(GenerationTask, task_id)
            task.progress = percent
            db.commit()

        for content in contents:
            workflow = GenerateWorkflow(progress_cb=progress_cb)
            result = workflow.run(content, options)
            # 汇总业务流程（FR-1.4）
            for r in result.requirements:
                flow = (r.get("business_flow") or "").strip()
                if flow:
                    business_flows.append({"no": r.get("no"), "name": r.get("name"), "flow": flow})
            # 汇总评审结果（FR-5）
            if result.review:
                reviews.append(result.review)
            # 测试点入库
            test_points_in_db: list[TestPoint] = []
            for tp in result.test_points:
                point = TestPoint(
                    document_id=document_ids[0],
                    project_id=task.project_id,
                    name=tp.get("name", "未命名测试点"),
                    type=tp.get("type", "function"),
                    description=tp.get("description"),
                )
                db.add(point)
                db.commit()
                db.refresh(point)
                test_points_in_db.append(point)

            # 用例入库
            point_index = 0
            for case in result.test_cases:
                point_id = test_points_in_db[point_index].id if test_points_in_db and point_index < len(test_points_in_db) else None
                saved = save_generated_case(db, task.project_id, case, point_id, user_id)
                generated_cases.append(
                    {"case_id": saved.id, "title": saved.title, "priority": saved.priority}
                )
                total_case += 1
                point_index += 1

        # 聚合评审汇总（FR-5.2 评审结果展示）
        review_summary: dict = {
            "overall_score": 0,
            "issues": [],
            "missing_coverage": [],
            "doc_reviews": [],
        }
        if reviews:
            scores = [r.get("overall_score") or 0 for r in reviews if isinstance(r.get("overall_score"), (int, float))]
            review_summary["overall_score"] = round(sum(scores) / len(scores), 1) if scores else 0
            for r in reviews:
                for it in (r.get("issues") or [])[:30]:
                    review_summary["issues"].append(it)
                for it in (r.get("missing_coverage") or [])[:15]:
                    if it not in review_summary["missing_coverage"]:
                        review_summary["missing_coverage"].append(it)
                review_summary["doc_reviews"].append(
                    {
                        "overall_score": r.get("overall_score", 0),
                        "conclusion": r.get("conclusion", ""),
                    }
                )

        task.total_case = total_case
        task.status = "success"
        task.progress = 100
        task.result_summary = {
            "total_case": total_case,
            "generated_cases": generated_cases[:200],
            "document_count": len(contents),
            "review": review_summary,
            "business_flows": business_flows[:30],
            "finished_at": datetime.now().isoformat(),
        }
        task.finished_at = datetime.now()
        db.commit()
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.rollback()
        task = db.get(GenerationTask, task_id)
        if task:
            task.status = "failed"
            task.error_msg = str(e)
            task.finished_at = datetime.now()
            db.commit()
    finally:
        db.close()


def start_task(task_id: int, document_ids: list[int], options: dict, user_id: int) -> None:
    """启动后台线程执行生成任务"""
    thread = threading.Thread(
        target=_run_workflow,
        args=(task_id, document_ids, options, user_id),
        daemon=True,
    )
    thread.start()


def get_task(db: Session, task_id: int) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise NotFoundError("任务不存在")
    return task


def cancel_task(db: Session, task_id: int) -> GenerationTask:
    task = get_task(db, task_id)
    if task.status in ("success", "failed", "cancelled"):
        raise BusinessError(f"任务已处于 {task.status} 状态，无法取消")
    task.status = "cancelled"
    task.finished_at = datetime.now()
    db.commit()
    db.refresh(task)
    return task


def list_tasks(
    db: Session,
    user_id: int | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[GenerationTask], int]:
    """分页查询任务历史；user_id 为空表示全部（管理员）"""
    from sqlalchemy import select

    stmt = select(GenerationTask)
    if user_id is not None:
        stmt = stmt.where(GenerationTask.created_by == user_id)
    if status:
        stmt = stmt.where(GenerationTask.status == status)
    total = len(db.scalars(stmt).all())
    rows = db.scalars(
        stmt.order_by(GenerationTask.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return list(rows), total


def retry_task(db: Session, task_id: int, user_id: int) -> GenerationTask:
    """重试失败/取消/悬挂的任务：基于持久化的 options 重新入队执行"""
    task = get_task(db, task_id)
    if task.status == "running" or task.status == "pending":
        raise BusinessError("任务仍在执行中，无法重试")
    if task.created_by != user_id and db.get(User, user_id).role != "admin":
        raise BusinessError("无权操作该任务")
    options = task.options or {}
    doc_ids = options.get("document_ids") or ([task.document_id] if task.document_id else [])
    if not doc_ids:
        raise BusinessError("任务缺少关联文档，无法重试")
    # 重置状态后重新入队
    task.status = "pending"
    task.progress = 0
    task.error_msg = None
    task.started_at = None
    task.finished_at = None
    db.commit()
    start_task(task.id, doc_ids, options, user_id)
    return task
