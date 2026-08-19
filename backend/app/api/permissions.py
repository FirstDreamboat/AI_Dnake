"""权限目录与成员权限接口"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_perm
from app.core.permissions import PERMISSION_CATALOG
from app.database import get_db
from app.models.user import User
from app.schemas.common import ok
from app.schemas.permission import PermissionUpdate
from app.services import auth_service

router = APIRouter()


@router.get("/permissions/catalog")
def permission_catalog(
    user: User = Depends(get_current_user),
):
    """权限点目录（供成员管理界面渲染勾选项）"""
    return ok(PERMISSION_CATALOG)


@router.get("/users/{user_id}/permissions")
def get_user_permissions(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("user_manage")),
):
    """获取成员自定义权限点列表"""
    user = db.get(User, user_id)
    if not user:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("用户不存在")
    return ok({"permissions": auth_service.get_user_permissions(db, user)})


@router.put("/users/{user_id}/permissions")
def set_user_permissions(
    user_id: int,
    req: PermissionUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_perm("user_manage")),
):
    """设置成员权限点（全量覆盖；admin 角色恒为全部权限，忽略请求）"""
    auth_service.set_user_permissions(db, user_id, req.permissions)
    return ok({"permissions": auth_service.get_user_permissions(db, db.get(User, user_id))}, "权限更新成功")
