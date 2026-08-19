"""操作日志服务"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operation_log import OperationLog


def create_log(
    db: Session,
    *,
    user_id: int | None = None,
    username: str | None = None,
    module: str = "",
    action: str = "",
    method: str = "",
    path: str = "",
    detail: str | None = None,
    ip: str | None = None,
    status_code: int = 200,
) -> OperationLog:
    log = OperationLog(
        user_id=user_id,
        username=username,
        module=module,
        action=action,
        method=method,
        path=path,
        detail=detail,
        ip=ip,
        status_code=status_code,
    )
    db.add(log)
    db.commit()
    return log


def list_logs(
    db: Session,
    page: int,
    page_size: int,
    module: str | None = None,
    username: str | None = None,
    keyword: str | None = None,
) -> tuple[list[dict], int]:
    stmt = select(OperationLog)
    if module:
        stmt = stmt.where(OperationLog.module == module)
    if username:
        stmt = stmt.where(OperationLog.username == username)
    if keyword:
        stmt = stmt.where(
            (OperationLog.action.contains(keyword))
            | (OperationLog.path.contains(keyword))
        )
    total = len(db.scalars(stmt).all())
    rows = db.scalars(
        stmt.order_by(OperationLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "username": r.username,
            "module": r.module,
            "action": r.action,
            "method": r.method,
            "path": r.path,
            "detail": r.detail,
            "ip": r.ip,
            "status_code": r.status_code,
            "created_at": r.created_at,
        }
        for r in rows
    ], total


def clear_logs(db: Session) -> int:
    """清空全部日志，返回删除条数"""
    count = len(db.scalars(select(OperationLog)).all())
    db.query(OperationLog).delete()
    db.commit()
    return count
