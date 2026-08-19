"""操作日志接口"""
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import require_perm, require_role
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.services import log_service

router = APIRouter()


@router.get("")
def list_logs(
    module: str | None = Query(None),
    username: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("logs")),
):
    """日志列表（需 logs 权限）"""
    rows, total = log_service.list_logs(db, page, page_size, module, username, keyword)
    return ok(PageData(list=rows, total=total, page=page, page_size=page_size))


@router.delete("")
def clear_logs(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """清空日志（仅管理员）"""
    count = log_service.clear_logs(db)
    return ok({"cleared": count}, f"已清空 {count} 条日志")


@router.get("/export")
def export_logs(
    module: str | None = Query(None),
    username: str | None = Query(None),
    keyword: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("logs")),
):
    """导出日志为 CSV（审计用，需 logs 权限）"""
    rows, _ = log_service.list_logs(db, 1, limit, module, username, keyword)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ID", "用户名", "模块", "动作", "方法", "路径", "详情", "IP", "状态码", "时间"])
    for r in rows:
        writer.writerow(
            [
                r["id"],
                r["username"] or "",
                r["module"],
                r["action"],
                r["method"],
                r["path"],
                (r["detail"] or "").replace("\n", " "),
                r["ip"] or "",
                r["status_code"],
                str(r["created_at"]),
            ]
        )
    data = buf.getvalue().encode("utf-8-sig")
    ts = int(__import__("time").time())
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="operation_logs_{ts}.csv"'},
    )
