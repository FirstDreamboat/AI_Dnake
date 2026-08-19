"""SSE 事件流服务"""
import json
import time

from app.database import SessionLocal
from app.models.generation_task import GenerationTask


def task_event_stream(task_id: int):
    """基于任务表 progress 字段的轮询式 SSE 推送"""
    last_progress = -1
    last_status = None
    while True:
        db = SessionLocal()
        try:
            task = db.get(GenerationTask, task_id)
            if not task:
                yield "event: error\ndata: {\"message\": \"任务不存在\"}\n\n"
                break
            progress = task.progress
            status = task.status
            if progress != last_progress:
                last_progress = progress
                yield f"event: progress\ndata: {json.dumps({'progress': progress, 'stage': _stage_name(progress), 'status': status})}\n\n"
            if status != last_status:
                last_status = status
                yield f"event: {status}\ndata: {json.dumps({'task_id': task_id, 'progress': progress, 'total_case': task.total_case, 'error': task.error_msg})}\n\n"
            if status in ("success", "failed", "cancelled"):
                yield "event: done\ndata: {}\n\n"
                break
        finally:
            db.close()
        time.sleep(1)


def _stage_name(progress: int) -> str:
    if progress < 10:
        return "pending"
    if progress < 30:
        return "requirement_parse"
    if progress < 45:
        return "test_point_extraction"
    if progress < 60:
        return "rag_retrieval"
    if progress < 85:
        return "case_generation"
    if progress < 100:
        return "case_review"
    return "complete"
