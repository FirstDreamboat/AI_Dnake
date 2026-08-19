"""成员管理接口"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_perm
from app.database import get_db
from app.models.user import User
from app.schemas.common import PageData, ok
from app.schemas.user import PasswordReset, UserCreate, UserStatusUpdate, UserUpdate
from app.services import auth_service

router = APIRouter()


@router.get("")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    keyword: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("user_manage")),
):
    users, total = auth_service.list_users(db, page, page_size, keyword)
    items = [auth_service.build_user_out(db, u) for u in users]
    return ok(PageData(list=items, total=total, page=page, page_size=page_size))


@router.post("")
def create_user(
    req: UserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("user_manage")),
):
    user = auth_service.create_user(db, req, admin)
    return ok(auth_service.build_user_out(db, user), "成员添加成功")


@router.put("/{user_id}")
def update_user(
    user_id: int,
    req: UserUpdate,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.id != user_id and current.role != "admin":
        from app.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError()
    # 仅管理员可通过编辑接口覆盖权限
    if req.permissions is not None and current.id != user_id and current.role != "admin":
        from app.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError()
    user = auth_service.update_user(db, user_id, req)
    return ok(auth_service.build_user_out(db, user), "成员更新成功")


@router.put("/{user_id}/password")
def reset_password(
    user_id: int,
    req: PasswordReset,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.id != user_id and current.role != "admin":
        from app.core.exceptions import PermissionDeniedError

        raise PermissionDeniedError()
    auth_service.reset_password(db, user_id, req.new_password)
    return ok(message="密码重置成功")


@router.put("/{user_id}/status")
def set_status(
    user_id: int,
    req: UserStatusUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("user_manage")),
):
    user = auth_service.set_user_active(db, user_id, req.is_active)
    return ok(auth_service.build_user_out(db, user), "状态更新成功")


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("user_manage")),
):
    auth_service.delete_user(db, user_id, admin)
    return ok(None, "成员删除成功")
