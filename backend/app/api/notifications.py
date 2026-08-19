"""消息通知接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.notification import NotificationOut
from app.services import notification_service

router = APIRouter()


@router.get("")
def list_notifications(
    page: int = 1,
    page_size: int = 20,
    only_unread: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页查询当前用户通知"""
    rows, total, unread = notification_service.list_notifications(
        db, user.id, page, page_size, only_unread
    )
    return ok(
        PageData(
            list=[NotificationOut.model_validate(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        ),
        message=f"未读 {unread}",
    )


@router.get("/unread-count")
def get_unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """当前用户未读通知数"""
    return ok({"unread": notification_service.unread_count(db, user.id)})


@router.put("/{notification_id}/read")
def read_notification(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标记单条通知已读"""
    notification_service.mark_read(db, notification_id, user.id)
    return ok(message="已标记为已读")


@router.put("/read-all")
def read_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """全部标记为已读"""
    count = notification_service.mark_all_read(db, user.id)
    return ok({"marked": count}, message=f"已标记 {count} 条为已读")
