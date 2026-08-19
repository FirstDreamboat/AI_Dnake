"""消息通知服务"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.notification import Notification


def create_notification(
    db: Session,
    user_id: int,
    category: str,
    title: str,
    content: str | None = None,
    related_id: int | None = None,
) -> Notification:
    """创建一条通知"""
    n = Notification(
        user_id=user_id,
        category=category,
        title=title,
        content=content,
        related_id=related_id,
        is_read=False,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def list_notifications(
    db: Session, user_id: int, page: int, page_size: int, only_unread: bool = False
) -> tuple[list[Notification], int, int]:
    """分页查询当前用户通知，返回 (列表, 总数, 未读数)"""
    stmt = select(Notification).where(Notification.user_id == user_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if only_unread:
        stmt = stmt.where(Notification.is_read.is_(False))
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ) or 0
    rows = (
        db.scalars(stmt.order_by(Notification.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
        .all()
    )
    return list(rows), total, unread


def mark_read(db: Session, notification_id: int, user_id: int) -> Notification:
    n = db.get(Notification, notification_id)
    if not n:
        raise NotFoundError("通知不存在")
    if n.user_id != user_id:
        raise NotFoundError("通知不存在")
    n.is_read = True
    db.commit()
    db.refresh(n)
    return n


def mark_all_read(db: Session, user_id: int) -> int:
    """将当前用户全部通知标记为已读，返回标记数量"""
    rows = db.scalars(
        select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ).all()
    for n in rows:
        n.is_read = True
    db.commit()
    return len(rows)


def unread_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ) or 0
