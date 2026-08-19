"""FastAPI 依赖注入：数据库会话、当前用户、权限校验"""
from collections.abc import Generator

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthError, PermissionDeniedError
from app.core.security import decode_token
from app.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 角色层级（数字越大权限越高）
ROLE_LEVEL = {"engineer": 1, "manager": 2, "admin": 3}


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 Token 中解析当前登录用户"""
    try:
        payload = decode_token(token)
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise AuthError("Token 无效或已过期")

    user = db.get(User, user_id)
    if not user:
        raise AuthError("用户不存在")
    if not user.is_active:
        raise AuthError("账号已被禁用")
    return user


def require_role(*roles: str):
    """角色权限校验装饰器: require_role("admin") 或 require_role("admin","manager")"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise PermissionDeniedError(f"需要 {'/'.join(roles)} 权限")
        return user

    return checker


def require_perm(*codes: str):
    """权限点校验装饰器: require_perm("statistics") 或 require_perm("logs","user_manage")

    admin 角色动态拥有全部权限；其他用户校验 user_permissions 表中是否包含任一权限点。
    """

    def checker(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if user.role == "admin":
            return user
        from app.models.user_permission import UserPermission

        owned = set(
            db.scalars(
                select(UserPermission.permission_code).where(UserPermission.user_id == user.id)
            ).all()
        )
        if not owned.intersection(set(codes)):
            raise PermissionDeniedError(f"需要 {'/'.join(codes)} 权限")
        return user

    return checker


def get_db_session(db: Session = Depends(get_db)) -> Generator[Session, None, None]:
    yield db
